"""Backend interface: the only boundary between our router and a model library."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BackendResult:
    text: str
    input_tokens: int
    output_tokens: int


class Backend(Protocol):
    def complete(
        self,
        *,
        route: str,
        messages: list[dict],
        api_base: str,
        api_key: str | None,
        max_tokens: int,
        temperature: float | None,
        reasoning_effort: str | None,
        timeout_s: float,
    ) -> BackendResult: ...
