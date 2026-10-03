import subprocess
import sys
import textwrap

import pytest

from app.core import startup_checks as sc
from app.core.config import PROJECT_ROOT
from app.core.logging import redact


@pytest.mark.parametrize("version", ["1.82.7", "1.82.8"])
def test_malicious_litellm_versions_are_blocked(version):
    result = sc.check_litellm_version(installed=version, expected=version)
    assert result.severity == "error" and "MALICIOUS" in result.detail


def test_old_litellm_is_blocked():
    assert sc.check_litellm_version(installed="1.80.0", expected="1.80.0").severity == "error"


def test_litellm_must_match_pin():
    assert sc.check_litellm_version(installed="1.102.2", expected="1.102.1").severity == "error"
    assert sc.check_litellm_version(installed="1.102.1", expected="1.102.1").ok


def test_pyproject_pins_clean_litellm_exactly():
    pinned = sc.pinned_version("litellm")
    assert pinned is not None
    assert pinned not in sc.BLOCKED_LITELLM_VERSIONS
    assert sc._version_tuple(pinned) >= sc.MIN_LITELLM_VERSION


def test_installed_environment_passes_litellm_check():
    assert sc.check_litellm_version().ok


def test_attack_pth_file_is_detected(tmp_path):
    (tmp_path / "_virtualenv.pth").write_text("")
    assert sc.check_pth_files([tmp_path]).ok
    (tmp_path / "litellm_init.pth").write_text("import os")
    assert sc.check_pth_files([tmp_path]).severity == "error"


def test_unexpected_pth_file_is_a_warning(tmp_path):
    (tmp_path / "something.pth").write_text("")
    assert sc.check_pth_files([tmp_path]).severity == "warning"


def test_keys_in_dotenv_are_an_error(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ATS_LOG_LEVEL=INFO\nOPENAI_API_KEY=sk-abcdefghijklmnopqrstuv\n")
    assert sc.check_keys_not_in_env(env={}, dotenv=env_file).severity == "error"
    env_file.write_text("ATS_LOG_LEVEL=INFO\n")
    assert sc.check_keys_not_in_env(env={}, dotenv=env_file).ok
    assert sc.check_keys_not_in_env(env={"OPENAI_API_KEY": "x"}, dotenv=env_file).severity == "warning"


@pytest.mark.parametrize(
    ("value", "severity"),
    [
        ("", "ok"),
        ("127.0.0.1:11434", "ok"),
        ("http://localhost:11434", "ok"),
        ("0.0.0.0", "warning"),
        ("0.0.0.0:11434", "warning"),
        ("192.168.1.5", "warning"),
    ],
)
def test_ollama_host(value, severity):
    assert sc.check_ollama_host(env={"OLLAMA_HOST": value} if value else {}).severity == severity


def test_project_streamlit_config_is_local_only():
    assert sc.check_streamlit_config().ok


def test_assert_safe_to_start_raises_on_error():
    bad = [sc.CheckResult("x", "error", "boom"), sc.CheckResult("y", "warning", "meh")]
    with pytest.raises(sc.StartupCheckError):
        sc.assert_safe_to_start(bad)
    assert sc.assert_safe_to_start([sc.CheckResult("y", "warning", "meh")])


def test_redaction():
    text = "key sk-proj-ABCDEFGH12345678 and hf_ABCDEFGHIJ and Bearer abc.def.ghi123"
    out = redact(text)
    assert (
        "sk-proj-ABCDEFGH12345678" not in out and "hf_ABCDEFGHIJ" not in out and "abc.def.ghi123" not in out
    )
    assert out.count("[REDACTED]") == 3


def test_litellm_import_and_call_make_no_unexpected_network_connections():
    """Importing our LiteLLM backend must not reach the internet (price list / headers come from the
    bundled copies). A mocked completion must not connect either."""
    code = textwrap.dedent(
        """
        import socket
        attempts = []
        _orig = socket.socket.connect
        def guard(self, address):
            attempts.append(address)
            raise OSError("network blocked by test")
        socket.socket.connect = guard
        socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))

        from app.llm.litellm_backend import litellm
        r = litellm.completion(model="openai/gpt-5-nano", messages=[{"role": "user", "content": "hi"}],
                               mock_response="ok", api_key="sk-test")
        assert r.choices[0].message.content == "ok"
        print("ATTEMPTS", attempts)
        assert not attempts, attempts
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
