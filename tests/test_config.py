import copy

import pytest

from app.core.config import PROJECT_ROOT
from app.llm.config import ModelsConfig, host_of, load_models_config
from tests.conftest import CONFIG


def test_project_models_yaml_is_valid():
    cfg = load_models_config(PROJECT_ROOT / "config" / "models.yaml")
    assert cfg.budget.monthly_usd_cap > 0
    assert "test_local" in cfg.tasks and "test_openai" in cfg.tasks
    # every provider host must be allow-listed; every premium model must have a price
    for provider in cfg.providers.values():
        assert provider.host in cfg.allowed_hosts
    for ref in cfg.premium_models:
        assert ref in cfg.prices


def test_paid_model_without_price_is_rejected():
    bad = copy.deepcopy(CONFIG)
    del bad["prices"]["openai/cheap"]
    with pytest.raises(ValueError, match="no entry in prices"):
        ModelsConfig.model_validate(bad)


def test_provider_host_must_be_allowlisted():
    bad = copy.deepcopy(CONFIG)
    bad["allowed_hosts"] = ["127.0.0.1:11434"]
    with pytest.raises(ValueError, match="not in allowed_hosts"):
        ModelsConfig.model_validate(bad)


def test_unknown_provider_is_rejected():
    bad = copy.deepcopy(CONFIG)
    bad["tasks"]["x"] = {"primary": "mystery/model"}
    with pytest.raises(ValueError, match="known provider"):
        ModelsConfig.model_validate(bad)


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("http://127.0.0.1:11434", "127.0.0.1:11434"),
        ("https://api.openai.com/v1", "api.openai.com"),
        ("https://router.huggingface.co/v1", "router.huggingface.co"),
    ],
)
def test_host_of(url, host):
    assert host_of(url) == host
