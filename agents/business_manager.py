from __future__ import annotations

import json
import os
import re
from typing import Any

from config.business_config import get_business_config

try:
    from openai import OpenAI
except ImportError:  # OpenAI is optional while LLM manager mode is disabled.
    OpenAI = None  # type: ignore[assignment]


class BusinessManagerAgent:
    """
    Policy and risk gate for commercial conversations.

    Default behavior is deterministic and makes zero OpenAI calls.
    Routine LLM decision support can be enabled in config/business.yaml.
    High-risk messages always escalate before any model call.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or get_business_config()

        self.business = self.config["business"]
        self.offer = self.config["offer"]
        self.scope = self.config["scope"]
        self.autonomy = self.config["autonomy"]
        self.risk = self.config["risk"]
        self.manager = self.config["manager"]

        self.model = os.getenv("BUSINESS_MANAGER_MODEL", self.manager["model"])
        self.use_llm = bool(self.manager["use_llm_for_routine_decisions"])
        self.max_history_chars = int(self.manager["max_history_chars"])

        api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.use_llm and api_key and OpenAI is not None:
            self.client = OpenAI(api_key=api_key)

    @staticmethod
    def _normalize(value: Any) -> str:
        return str(value or "").strip()

    def _deterministic_risk(self, text: str) -> tuple[str, list[str]]:
        haystack = self._normalize(text).lower()
        matched: list[str] = []

        for pattern in self.risk["high_risk_patterns"]:
            try:
                if re.search(pattern, haystack, flags=re.IGNORECASE):
                    matched.append(pattern)
            except re.error:
                # Invalid customer-supplied/custom config regex should fail safe.
                matched.append(f"INVALID_REGEX:{pattern}")

        return ("high", matched) if matched else ("low", [])

    def _timeline_text(self) -> str:
        days = int(self.offer["max_delivery_days"])
        return f"up to {days} days"

    def _price_text(self) -> str:
        currency = self._normalize(self.offer.get("currency")) or "USD"
        price = self.offer.get("price", 0)
        return f"{price} {currency}"

    def _base_decision(self) -> dict[str, Any]:
        return {
            "business_name": self.business["name"],
            "offer_name": self.offer["name"],
            "price": self.offer["price"],
            "currency": self.offer.get("currency", "USD"),
            "price_policy": self.offer.get("price_policy", "fixed"),
            "timeline": self._timeline_text(),
            "approved_scope": list(self.scope["approved"]),
            "excluded_scope": list(self.scope["excluded"]),
            "allowed_next_actions": list(self.autonomy["allowed_next_actions"]),
            "forbidden_autonomous_actions": list(self.autonomy["forbidden_actions"]),
            "approved_commitments": [
                f"Configured price is {self._price_text()}",
                f"Configured delivery timeline is {self._timeline_text()}",
                "Only approved scope may be promised autonomously",
                "Passwords, API keys, secrets, and credentials must not be requested",
            ],
            "unapproved_commitments": [
                "Unconfigured discounts or price changes",
                "Guaranteed business outcomes",
                "Refund promises",
                "Contract or legal acceptance",
                "Financial commitments",
                "Out-of-scope custom work",
                "Credentials or secrets",
            ],
        }

    def decide(
        self,
        latest_customer_message: str,
        intent: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        latest_customer_message = self._normalize(latest_customer_message)
        intent = self._normalize(intent) or "unclear"

        deterministic_risk, matched_patterns = self._deterministic_risk(
            latest_customer_message
        )

        decision = self._base_decision()
        decision.update(
            {
                "ok": True,
                "agent": "Business Manager Agent",
                "model": self.model if self.use_llm else None,
                "llm_enabled": self.use_llm,
                "llm_called": False,
                "intent": intent,
                "risk_level": deterministic_risk,
                "human_required": deterministic_risk == "high",
                "matched_risk_patterns": matched_patterns,
                "recommended_next_action": "answer_standard_questions",
                "manager_note": (
                    "Use only configured scope, price, timeline, and allowed actions. "
                    "Escalate any unapproved commercial commitment."
                ),
            }
        )

        # High-risk requests stop here. No LLM call is allowed.
        if deterministic_risk == "high":
            decision["recommended_next_action"] = "escalate_to_human"
            return decision

        # Default commercial mode: deterministic, zero LLM cost.
        if not self.use_llm:
            return decision

        # LLM was requested in config, but it is unavailable: safe fallback.
        if self.client is None:
            decision["manager_warning"] = (
                "LLM manager mode is enabled but OpenAI client/API key is unavailable; "
                "using deterministic policy fallback."
            )
            return decision

        history_lines: list[str] = []
        for item in (conversation_history or [])[-12:]:
            if not isinstance(item, dict):
                continue
            direction = self._normalize(item.get("direction"))
            body = self._normalize(item.get("body"))
            if direction in {"inbound", "outbound"} and body:
                history_lines.append(f"{direction}: {body}")

        history_text = "\n".join(history_lines)[-self.max_history_chars :]

        prompt = {
            "role": f"You are the Business Manager for {self.business['name']}.",
            "task": (
                "Choose the safest standard next business action. "
                "Choose only from allowed_next_actions. Do not change configured "
                "price, scope, timeline, legal position, or financial policy."
            ),
            "current_policy": {
                "offer_name": self.offer["name"],
                "price": self.offer["price"],
                "currency": self.offer.get("currency", "USD"),
                "timeline": self._timeline_text(),
                "approved_scope": self.scope["approved"],
                "excluded_scope": self.scope["excluded"],
                "allowed_next_actions": self.autonomy["allowed_next_actions"],
                "forbidden_autonomous_actions": self.autonomy["forbidden_actions"],
            },
            "intent": intent,
            "conversation_history": history_text,
            "latest_customer_message": latest_customer_message,
            "required_json": {
                "recommended_next_action": "one allowed action",
                "manager_note": "short instruction for the conversation agent",
            },
        }

        try:
            response = self.client.responses.create(
                model=self.model,
                input=json.dumps(prompt, ensure_ascii=False),
            )
            decision["llm_called"] = True

            raw = (response.output_text or "").strip()
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                return decision

            model_decision = json.loads(match.group(0))
            proposed_action = self._normalize(
                model_decision.get("recommended_next_action")
            )

            if proposed_action in self.autonomy["allowed_next_actions"]:
                decision["recommended_next_action"] = proposed_action

            note = self._normalize(model_decision.get("manager_note"))
            if note:
                decision["manager_note"] = note[:1000]

        except Exception as exc:
            decision["manager_warning"] = f"manager_model_fallback: {exc}"

        return decision
