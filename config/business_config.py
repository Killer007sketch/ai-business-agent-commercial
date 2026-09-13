from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).with_name("business.yaml")


class BusinessConfigError(RuntimeError):
    """Raised when the commercial business configuration is invalid."""


def _require_mapping(data: Any, key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise BusinessConfigError(f"Missing or invalid '{key}' section in business config")
    return value


def _require_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BusinessConfigError(f"'{key}' must be a list of strings")
    return value


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    business = _require_mapping(data, "business")
    offer = _require_mapping(data, "offer")
    scope = _require_mapping(data, "scope")
    autonomy = _require_mapping(data, "autonomy")
    risk = _require_mapping(data, "risk")
    manager = _require_mapping(data, "manager")
    proposal_agent = _require_mapping(data, "proposal_agent")

    if not str(business.get("name") or "").strip():
        raise BusinessConfigError("business.name is required")
    if not str(offer.get("name") or "").strip():
        raise BusinessConfigError("offer.name is required")
    if float(offer.get("price", 0)) < 0:
        raise BusinessConfigError("offer.price cannot be negative")
    if int(offer.get("max_delivery_days", 0)) <= 0:
        raise BusinessConfigError("offer.max_delivery_days must be greater than zero")

    _require_list(scope, "approved")
    _require_list(scope, "excluded")
    _require_list(autonomy, "allowed_next_actions")
    _require_list(autonomy, "forbidden_actions")
    _require_list(risk, "high_risk_patterns")

    manager["use_llm_for_routine_decisions"] = bool(
        manager.get("use_llm_for_routine_decisions", False)
    )
    manager["model"] = str(manager.get("model") or "gpt-5-mini")
    manager["max_history_chars"] = int(manager.get("max_history_chars", 8000))

    proposal_agent["model"] = str(proposal_agent.get("model") or "gpt-5-mini")
    proposal_agent["max_opportunities"] = int(proposal_agent.get("max_opportunities", 5))
    proposal_agent["max_problem_chars"] = int(proposal_agent.get("max_problem_chars", 1200))
    proposal_agent["max_requirements"] = int(proposal_agent.get("max_requirements", 12))
    proposal_agent["proposal_min_words"] = int(proposal_agent.get("proposal_min_words", 80))
    proposal_agent["proposal_max_words"] = int(proposal_agent.get("proposal_max_words", 140))

    if not 1 <= proposal_agent["max_opportunities"] <= 5:
        raise BusinessConfigError("proposal_agent.max_opportunities must be between 1 and 5")
    if proposal_agent["max_problem_chars"] <= 0:
        raise BusinessConfigError("proposal_agent.max_problem_chars must be greater than zero")
    if proposal_agent["max_requirements"] <= 0:
        raise BusinessConfigError("proposal_agent.max_requirements must be greater than zero")
    if proposal_agent["proposal_min_words"] <= 0:
        raise BusinessConfigError("proposal_agent.proposal_min_words must be greater than zero")
    if proposal_agent["proposal_max_words"] < proposal_agent["proposal_min_words"]:
        raise BusinessConfigError("proposal_agent.proposal_max_words must be >= proposal_min_words")

    return data


@lru_cache(maxsize=1)
def load_business_config() -> dict[str, Any]:
    configured_path = os.getenv("BUSINESS_CONFIG_PATH")
    path = Path(configured_path).expanduser() if configured_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise BusinessConfigError(f"Business config not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise BusinessConfigError("Business config root must be a mapping")

    return _validate(loaded)


def get_business_config() -> dict[str, Any]:
    """Return a defensive copy so callers cannot mutate the cached config."""
    return deepcopy(load_business_config())
