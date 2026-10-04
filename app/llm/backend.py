"""Backend interface: the only boundary between our router and a model library."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BackendResult:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]
    input_tokens: int


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
        extra_options: dict | None = None,
        json_output: bool = False,
    ) -> BackendResult: ...

    def embed(
        self,
        *,
        route: str,
        texts: list[str],
        api_base: str,
        api_key: str | None,
        timeout_s: float,
    ) -> EmbedResult: ...
