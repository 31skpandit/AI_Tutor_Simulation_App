"""Verify that every model in config/models.yaml exists, and cross-check prices.

    uv run python -m app.tools.verify_models

Checks (no tokens are spent):
  1. Ollama models used in the config are installed locally.
  2. OpenAI models used in the config are available to your key (needs the key in Credential Manager).
  3. Prices in the config match LiteLLM's bundled price list (differences are flagged for you to check
     against the official OpenAI pricing page).
"""

import sys
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.secrets import get_secret
from app.core.startup_checks import assert_safe_to_start
from app.llm.config import ModelsConfig, load_models_config
from app.llm.health import configured_models, ollama_has, ollama_models, openai_models


@dataclass(frozen=True)
class Finding:
    level: str  # "ok" | "warning" | "error"
    message: str


def verify(config: ModelsConfig) -> list[Finding]:
    findings: list[Finding] = []

    ollama = config.providers.get("ollama")
    if ollama:
        installed = ollama_models(ollama.api_base)
        if installed is None:
            findings.append(Finding("error", f"Ollama not reachable at {ollama.api_base} — is it running?"))
        else:
            for model in configured_models(config, "ollama"):
                ok = ollama_has(installed, model)
                findings.append(
                    Finding(
                        "ok" if ok else "error",
                        f"ollama/{model}: {'installed' if ok else 'NOT installed — run: ollama pull ' + model}",
                    )
                )

    openai = config.providers.get("openai")
    if openai:
        key = get_secret(openai.secret) if openai.secret else None
        if not key:
            findings.append(Finding("warning", "OpenAI key not stored yet — cannot check model availability"))
        else:
            try:
                available = set(openai_models(openai.api_base, key))
            except httpx.HTTPStatusError as exc:
                findings.append(
                    Finding(
                        "error", f"OpenAI /models returned HTTP {exc.response.status_code} — check the key"
                    )
                )
            except httpx.HTTPError as exc:
                findings.append(Finding("error", f"OpenAI not reachable: {type(exc).__name__}"))
            else:
                for model in configured_models(config, "openai"):
                    ok = model in available
                    findings.append(
                        Finding(
                            "ok" if ok else "error",
                            f"openai/{model}: {'available to your key' if ok else 'NOT available to your key'}",
                        )
                    )

    from app.llm.litellm_backend import bundled_price

    for ref, price in sorted(config.prices.items()):
        bundled = bundled_price(ref.partition("/")[2])
        configured = (price.input_per_million, price.output_per_million)
        if bundled is None:
            findings.append(Finding("warning", f"{ref}: not in LiteLLM price list — verify price manually"))
        elif abs(bundled[0] - configured[0]) > 1e-9 or abs(bundled[1] - configured[1]) > 1e-9:
            findings.append(
                Finding(
                    "warning",
                    f"{ref}: config ${configured[0]}/${configured[1]} vs LiteLLM "
                    f"${bundled[0]}/${bundled[1]} per 1M — check official pricing",
                )
            )
        else:
            findings.append(
                Finding("ok", f"{ref}: price ${configured[0]} in / ${configured[1]} out per 1M (matches)")
            )
    return findings


def main() -> int:
    settings = get_settings()
    assert_safe_to_start()
    findings = verify(load_models_config(settings.models_config))
    labels = {"ok": "OK  ", "warning": "WARN", "error": "FAIL"}
    for f in findings:
        print(f"[{labels[f.level]}] {f.message}")
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
