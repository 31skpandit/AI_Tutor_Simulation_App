"""API-key storage in Windows Credential Manager via `keyring` (blueprint §14.4).

Keys are never written to files or environment variables. They are read only at the moment
a model call needs them.

Command line:
    uv run python -m app.core.secrets set openai     # prompts for the key (input hidden)
    uv run python -m app.core.secrets status
    uv run python -m app.core.secrets delete openai
"""

import getpass
import sys

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "ai-teaching-studio"

KNOWN_SECRETS: dict[str, str] = {
    "openai": "OpenAI API key",
    "huggingface": "Hugging Face access token",
    "gemini": "Google Gemini API key",
    "groq": "Groq API key",
    "openrouter": "OpenRouter API key",
}


def _check_name(name: str) -> None:
    if name not in KNOWN_SECRETS:
        raise ValueError(f"Unknown secret '{name}'. Known: {', '.join(KNOWN_SECRETS)}")


def get_secret(name: str) -> str | None:
    _check_name(name)
    return keyring.get_password(SERVICE, name)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def set_secret(name: str, value: str) -> None:
    _check_name(name)
    value = value.strip()
    if not value:
        raise ValueError("Empty value; nothing stored.")
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> bool:
    _check_name(name)
    try:
        keyring.delete_password(SERVICE, name)
        return True
    except PasswordDeleteError:
        return False


def backend_name() -> str:
    kr = keyring.get_keyring()
    return f"{type(kr).__module__}.{type(kr).__name__}"


def _main(argv: list[str]) -> int:
    if len(argv) < 1 or argv[0] not in {"set", "delete", "status"}:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "status":
        print(f"Backend: {backend_name()}")
        for name, label in KNOWN_SECRETS.items():
            print(f"  {name:12} {'stored' if has_secret(name) else '-':8} {label}")
        return 0
    if len(argv) != 2:
        print(f"Usage: python -m app.core.secrets {cmd} <name>")
        return 2
    name = argv[1]
    if cmd == "set":
        set_secret(name, getpass.getpass(f"Paste {KNOWN_SECRETS.get(name, name)} (input hidden): "))
        print(f"Stored '{name}' in Windows Credential Manager.")
    else:
        print("Deleted." if delete_secret(name) else "Nothing stored under that name.")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
