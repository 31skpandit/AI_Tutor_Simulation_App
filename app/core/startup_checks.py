"""Security checks run before any AI call is allowed (blueprint §14.3–14.5).

These checks never import `litellm` — they inspect package metadata and files only, so a
compromised package cannot run code during the check itself.

Command line:  uv run python -m app.core.startup_checks
"""

import importlib.metadata
import os
import re
import site
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.config import PROJECT_ROOT

BLOCKED_LITELLM_VERSIONS = {"1.82.7", "1.82.8"}  # malicious releases, 24 March 2026
MIN_LITELLM_VERSION = (1, 83, 0)
SUSPICIOUS_PTH_FILES = {"litellm_init.pth"}
EXPECTED_PTH_FILES = {"_virtualenv.pth"}  # created by uv for the virtual environment
KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

Severity = Literal["ok", "warning", "error"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: Severity
    detail: str

    @property
    def ok(self) -> bool:
        return self.severity == "ok"


class StartupCheckError(RuntimeError):
    def __init__(self, failures: list[CheckResult]):
        self.failures = failures
        super().__init__("; ".join(f"{f.name}: {f.detail}" for f in failures))


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def pinned_version(package: str, pyproject: Path = PROJECT_ROOT / "pyproject.toml") -> str | None:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    for dep in data.get("project", {}).get("dependencies", []):
        match = re.fullmatch(rf"\s*{re.escape(package)}\s*==\s*([^\s;]+)\s*", dep)
        if match:
            return match.group(1)
    return None


def check_litellm_version(installed: str | None = None, expected: str | None = None) -> CheckResult:
    name = "LiteLLM version"
    if installed is None:
        try:
            installed = importlib.metadata.version("litellm")
        except importlib.metadata.PackageNotFoundError:
            return CheckResult(name, "error", "litellm is not installed")
    if expected is None:
        expected = pinned_version("litellm")
    if installed in BLOCKED_LITELLM_VERSIONS:
        return CheckResult(
            name, "error", f"{installed} is a known MALICIOUS release — remove the environment now"
        )
    if _version_tuple(installed) < MIN_LITELLM_VERSION:
        return CheckResult(name, "error", f"{installed} is older than the minimum clean version 1.83.0")
    if expected is None:
        return CheckResult(name, "error", "litellm is not pinned with '==' in pyproject.toml")
    if installed != expected:
        return CheckResult(
            name, "error", f"installed {installed} differs from pinned {expected}; run `uv sync --locked`"
        )
    return CheckResult(name, "ok", f"{installed} (pinned, clean)")


def _site_dirs() -> list[Path]:
    dirs = {Path(p) for p in site.getsitepackages()}
    user_site = site.getusersitepackages()
    if user_site:
        dirs.add(Path(user_site))
    return sorted(d for d in dirs if d.is_dir())


def check_pth_files(site_dirs: list[Path] | None = None) -> CheckResult:
    name = "Startup (.pth) files"
    found = [p for d in (site_dirs if site_dirs is not None else _site_dirs()) for p in d.glob("*.pth")]
    suspicious = sorted(p.name for p in found if p.name in SUSPICIOUS_PTH_FILES)
    if suspicious:
        return CheckResult(name, "error", f"known attack file(s) present: {', '.join(suspicious)}")
    unexpected = sorted(p.name for p in found if p.name not in EXPECTED_PTH_FILES)
    if unexpected:
        return CheckResult(name, "warning", f"review unexpected .pth file(s): {', '.join(unexpected)}")
    return CheckResult(name, "ok", "only expected files present")


def check_keys_not_in_env(
    env: dict[str, str] | None = None, dotenv: Path = PROJECT_ROOT / ".env"
) -> CheckResult:
    name = "API keys outside files/env"
    env = dict(os.environ) if env is None else env
    in_env = [var for var in KEY_ENV_VARS if env.get(var)]
    in_file: list[str] = []
    if dotenv.is_file():
        text = dotenv.read_text(encoding="utf-8", errors="ignore")
        in_file = [var for var in KEY_ENV_VARS if re.search(rf"^\s*{var}\s*=\s*\S", text, re.M)]
        if re.search(
            r"sk-[A-Za-z0-9_\-]{8,}|hf_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_\-]{20,}|gsk_[A-Za-z0-9]{8,}", text
        ):
            in_file.append("a value that looks like an API key")
    if in_file:
        return CheckResult(
            name, "error", f".env contains {', '.join(in_file)} — move keys to Credential Manager"
        )
    if in_env:
        return CheckResult(
            name,
            "warning",
            f"environment variables set: {', '.join(in_env)} (not used by this app; remove them)",
        )
    return CheckResult(name, "ok", "no keys in .env or environment")


def check_ollama_host(env: dict[str, str] | None = None) -> CheckResult:
    name = "Ollama bound to localhost"
    value = (os.environ if env is None else env).get("OLLAMA_HOST", "").strip()
    if not value:
        return CheckResult(name, "ok", "OLLAMA_HOST not set (default 127.0.0.1:11434)")
    host = (
        re.sub(r"^https?://", "", value).rsplit(":", 1)[0]
        if not value.startswith("[")
        else value.split("]")[0] + "]"
    )
    if host in LOOPBACK_HOSTS:
        return CheckResult(name, "ok", f"OLLAMA_HOST={value}")
    return CheckResult(name, "warning", f"OLLAMA_HOST={value} exposes Ollama to the network; unset it")


def check_streamlit_config(path: Path = PROJECT_ROOT / ".streamlit" / "config.toml") -> CheckResult:
    name = "App reachable only from this laptop"
    if not path.is_file():
        return CheckResult(name, "warning", f"{path.name} missing")
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    problems = []
    if cfg.get("server", {}).get("address") not in {"127.0.0.1", "localhost"}:
        problems.append("server.address is not 127.0.0.1")
    if cfg.get("browser", {}).get("gatherUsageStats") is not False:
        problems.append("browser.gatherUsageStats is not false")
    if problems:
        return CheckResult(name, "warning", "; ".join(problems))
    return CheckResult(name, "ok", "Streamlit bound to 127.0.0.1, usage stats off")


def check_keyring_backend() -> CheckResult:
    name = "Secret storage"
    from app.core.secrets import backend_name

    backend = backend_name()
    if backend.endswith("WinVaultKeyring"):
        return CheckResult(name, "ok", "Windows Credential Manager")
    if sys.platform != "win32" and "fail" not in backend.lower() and "null" not in backend.lower():
        return CheckResult(name, "ok", backend)
    return CheckResult(name, "warning", f"unexpected keyring backend: {backend}")


def run_all() -> list[CheckResult]:
    return [
        check_litellm_version(),
        check_pth_files(),
        check_keys_not_in_env(),
        check_ollama_host(),
        check_streamlit_config(),
        check_keyring_backend(),
    ]


def assert_safe_to_start(results: list[CheckResult] | None = None) -> list[CheckResult]:
    results = run_all() if results is None else results
    failures = [r for r in results if r.severity == "error"]
    if failures:
        raise StartupCheckError(failures)
    return results


if __name__ == "__main__":
    symbols = {"ok": "OK  ", "warning": "WARN", "error": "FAIL"}
    results = run_all()
    for r in results:
        print(f"[{symbols[r.severity]}] {r.name}: {r.detail}")
    sys.exit(1 if any(r.severity == "error" for r in results) else 0)
