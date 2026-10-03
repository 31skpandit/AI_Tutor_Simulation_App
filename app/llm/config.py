"""Typed loader for config/models.yaml."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, model_validator


class ProviderConfig(BaseModel):
    litellm_prefix: str  # LiteLLM route prefix, e.g. "ollama_chat" or "openai"
    api_base: str
    secret: str | None = None  # name in Credential Manager; None = no key needed
    paid: bool = False

    @property
    def host(self) -> str:
        return host_of(self.api_base)


class Price(BaseModel):
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)


class TaskConfig(BaseModel):
    primary: str
    fallbacks: list[str] = []
    max_tokens: int = Field(default=800, gt=0)
    temperature: float | None = None
    # OpenAI reasoning models: how much hidden reasoning to spend. For Ollama, None/"minimal" = thinking off.
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    cache: bool = True

    @property
    def chain(self) -> list[str]:
        return [self.primary, *self.fallbacks]


class BudgetConfig(BaseModel):
    monthly_usd_cap: float = Field(ge=0)
    premium_requires_approval: bool = True


class ModelsConfig(BaseModel):
    budget: BudgetConfig
    allowed_hosts: list[str]
    providers: dict[str, ProviderConfig]
    premium_models: list[str] = []
    prices: dict[str, Price] = {}
    tasks: dict[str, TaskConfig]

    @model_validator(mode="after")
    def _validate(self) -> "ModelsConfig":
        errors = []
        for name, provider in self.providers.items():
            if provider.host not in self.allowed_hosts:
                errors.append(f"provider '{name}' host '{provider.host}' is not in allowed_hosts")
        for task_name, task in self.tasks.items():
            for ref in task.chain:
                provider_name, _, model = ref.partition("/")
                if not model or provider_name not in self.providers:
                    errors.append(
                        f"task '{task_name}': '{ref}' must look like '<provider>/<model>' with a known provider"
                    )
                elif self.providers[provider_name].paid and ref not in self.prices:
                    errors.append(f"task '{task_name}': paid model '{ref}' has no entry in prices")
        if errors:
            raise ValueError("models.yaml: " + "; ".join(errors))
        return self

    def provider_of(self, model_ref: str) -> tuple[str, ProviderConfig, str]:
        provider_name, _, model = model_ref.partition("/")
        return provider_name, self.providers[provider_name], model


def host_of(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return f"{host}:{parts.port}" if parts.port else host


def load_models_config(path: Path) -> ModelsConfig:
    return ModelsConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
