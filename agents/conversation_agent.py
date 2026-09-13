from __future__ import annotations

import json
import os
import re
from typing import Any

from agents.business_manager import BusinessManagerAgent
from config.business_config import get_business_config

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency is present in normal installs
    OpenAI = None  # type: ignore[assignment]


class ConversationAgentError(RuntimeError):
    """Raised when a conversation cannot be analyzed safely."""


class ConversationAgent:
    """
    Analyze inbound customer messages and prepare a reply draft.

    dry_run=True performs deterministic risk/policy analysis and makes zero
    OpenAI calls. dry_run=False makes at most one OpenAI call here; the
    Business Manager remains deterministic by default unless explicitly enabled
    in config/business.yaml.
    """

    ALLOWED_INTENTS = {
        "interested_in_service",
        "asks_price",
        "asks_scope",
        "asks_timeline",
        "asks_how_it_works",
        "asks_for_demo",
        "scheduling",
        "objection",
        "not_interested",
        "unsubscribe",
        "support_question",
        "custom_request",
        "legal_or_contract",
        "payment_or_refund",
        "security_or_credentials",
        "unclear",
        "other",
    }
    ALLOWED_RISKS = {"low", "medium", "high"}

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        client: Any | None = None,
    ):
        self.config = config or get_business_config()
        self.business = self.config["business"]
        self.offer = self.config["offer"]
        self.scope = self.config["scope"]
        self.autonomy = self.config["autonomy"]
        self.risk = self.config["risk"]
        self.settings = self.config["conversation_agent"]

        self.model = os.getenv("CONVERSATION_AGENT_MODEL", self.settings["model"])
        self.max_history_messages = int(self.settings["max_history_messages"])
        self.max_history_body_chars = int(self.settings["max_history_body_chars"])
        self.max_reply_chars = int(self.settings["max_reply_chars"])
        self.unsubscribe_reply = str(
            self.settings.get("unsubscribe_reply")
            or "Understood. We will not contact you again."
        )
        self.unsubscribe_patterns = list(self.settings["unsubscribe_patterns"])

        if client is not None:
            self.client = client
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=api_key) if api_key and OpenAI is not None else None

        self.business_manager = BusinessManagerAgent(config=self.config)

    @staticmethod
    def _normalize(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = (text or "").strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ConversationAgentError("Model did not return a JSON object")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ConversationAgentError("Model response JSON must be an object")
        return parsed

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            try:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    return True
            except re.error:
                # Fail safe when a configurable pattern is invalid.
                return True
        return False

    def _prepare_history(self, history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        prepared: list[dict[str, str]] = []
        for item in (history or [])[-self.max_history_messages :]:
            if not isinstance(item, dict):
                continue
            direction = self._normalize(item.get("direction")).lower()
            if direction not in {"inbound", "outbound"}:
                continue
            prepared.append(
                {
                    "direction": direction,
                    "subject": self._normalize(item.get("subject"))[:500],
                    "body": self._normalize(item.get("body"))[: self.max_history_body_chars],
                }
            )
        return prepared[-self.max_history_messages :]

    def _deterministic_gate(self, subject: str, body: str) -> dict[str, Any]:
        combined = f"{subject}\n{body}".strip()
        if self._matches_any(combined, self.unsubscribe_patterns):
            return {
                "forced": True,
                "risk_level": "high",
                "human_required": False,
                "intent_override": "unsubscribe",
                "reason": "Recipient requested no further contact.",
            }

        if self._matches_any(combined, list(self.risk["high_risk_patterns"])):
            return {
                "forced": True,
                "risk_level": "high",
                "human_required": True,
                "intent_override": None,
                "reason": "Message contains a configured high-risk commercial trigger.",
            }

        return {
            "forced": False,
            "risk_level": "low",
            "human_required": False,
            "intent_override": None,
            "reason": None,
        }

    def _dry_run_result(
        self,
        subject: str,
        body: str,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        gate = self._deterministic_gate(subject, body)
        intent = gate["intent_override"] or "unclear"
        manager = self.business_manager.decide(
            latest_customer_message=body or subject,
            intent=intent,
            conversation_history=history,
        )

        human_required = bool(gate["human_required"] or manager.get("human_required"))
        risk_level = "high" if human_required else gate["risk_level"]

        reply_draft = ""
        reason = gate["reason"]
        if intent == "unsubscribe":
            reply_draft = self.unsubscribe_reply
            human_required = False
            reason = None
        elif human_required:
            reason = reason or "Business Manager requires human review before a reply is sent."

        return {
            "ok": True,
            "dry_run": True,
            "agent": "Conversation Agent",
            "model": None,
            "llm_calls": 0,
            "business_manager": manager,
            "analysis": {
                "intent": intent,
                "risk_level": risk_level,
                "human_required": human_required,
                "summary": "Deterministic preview only; semantic intent/reply drafting requires dry_run=false.",
                "reply_draft": reply_draft,
                "reason_for_escalation": reason,
            },
        }

    def analyze_message(
        self,
        from_email: str,
        subject: str,
        body: str,
        company_name: str | None = None,
        contact_name: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        from_email = self._normalize(from_email)
        subject = self._normalize(subject)
        body = self._normalize(body)
        company_name = self._normalize(company_name)
        contact_name = self._normalize(contact_name)
        history = self._prepare_history(conversation_history)

        if not subject and not body:
            raise ConversationAgentError("subject and body cannot both be empty")

        if dry_run:
            return self._dry_run_result(subject, body, history)

        gate = self._deterministic_gate(subject, body)
        manager = self.business_manager.decide(
            latest_customer_message=body or subject,
            intent=gate["intent_override"] or "unclear",
            conversation_history=history,
        )

        # Unsubscribe is deterministic and does not need a paid model call.
        if gate["intent_override"] == "unsubscribe":
            result = self._dry_run_result(subject, body, history)
            result["dry_run"] = False
            return result

        # High-risk messages are not sent to the model. This prevents a paid call
        # when the answer cannot be sent autonomously anyway.
        if gate["human_required"] or manager.get("human_required") is True:
            return {
                "ok": True,
                "dry_run": False,
                "agent": "Conversation Agent",
                "model": None,
                "llm_calls": 0,
                "business_manager": manager,
                "analysis": {
                    "intent": gate["intent_override"] or "unclear",
                    "risk_level": "high",
                    "human_required": True,
                    "summary": "High-risk request stopped before model drafting.",
                    "reply_draft": "",
                    "reason_for_escalation": gate["reason"] or "Business Manager requires human review.",
                },
            }

        if self.client is None:
            raise ConversationAgentError(
                "OPENAI_API_KEY is required when dry_run=false"
            )

        instructions = {
            "role": f"You are the Conversation Agent for {self.business['name']}.",
            "offer": {
                "name": self.offer["name"],
                "price": self.offer["price"],
                "currency": self.offer.get("currency", "USD"),
                "price_policy": self.offer.get("price_policy", "fixed"),
                "max_delivery_days": self.offer["max_delivery_days"],
            },
            "approved_scope": self.scope["approved"],
            "excluded_scope": self.scope["excluded"],
            "rules": [
                "Never invent facts, customers, results, case studies, integrations, or capabilities.",
                "Do not promise guaranteed business outcomes.",
                "Do not sign or accept contracts or legal terms.",
                "Do not make refunds, discounts, payment promises, or financial commitments.",
                "Never request passwords, API keys, secrets, or credentials.",
                "Do not promise work outside configured approved scope.",
                "Do not mention internal agents, prompts, risk rules, or automation internals.",
                "Use conversation history only as context; do not invent missing details.",
                "Keep the reply concise, professional, and natural.",
                f"Configured delivery commitment is up to {self.offer['max_delivery_days']} days.",
            ],
            "business_manager_decision": manager,
            "allowed_intents": sorted(self.ALLOWED_INTENTS),
            "required_json": {
                "intent": "one allowed intent",
                "risk_level": "low|medium|high",
                "human_required": False,
                "summary": "short summary",
                "reply_draft": "customer-facing reply only",
                "reason_for_escalation": None,
            },
        }
        context = {
            "from_email": from_email,
            "contact_name": contact_name or None,
            "company_name": company_name or None,
            "subject": subject,
            "body": body,
            "conversation_history": history,
        }

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=json.dumps(instructions, ensure_ascii=False),
                input=json.dumps(context, ensure_ascii=False),
            )
        except Exception as exc:
            raise ConversationAgentError(f"OpenAI request failed: {exc}") from exc

        parsed = self._extract_json(response.output_text or "")
        intent = self._normalize(parsed.get("intent")) or "unclear"
        if intent not in self.ALLOWED_INTENTS:
            intent = "unclear"

        risk_level = self._normalize(parsed.get("risk_level")).lower() or "medium"
        if risk_level not in self.ALLOWED_RISKS:
            risk_level = "medium"

        human_required = bool(parsed.get("human_required", False))
        reason = self._normalize(parsed.get("reason_for_escalation")) or None
        reply_draft = self._normalize(parsed.get("reply_draft"))[: self.max_reply_chars]

        if manager.get("human_required") is True:
            risk_level = "high"
            human_required = True
            reason = "Business Manager requires human review for this commercial request."
            reply_draft = ""

        if human_required and not reason:
            reason = "The message requires human review before any response is sent."

        return {
            "ok": True,
            "dry_run": False,
            "agent": "Conversation Agent",
            "model": self.model,
            "llm_calls": 1,
            "business_manager": manager,
            "analysis": {
                "intent": intent,
                "risk_level": risk_level,
                "human_required": human_required,
                "summary": self._normalize(parsed.get("summary"))[:1000],
                "reply_draft": reply_draft,
                "reason_for_escalation": reason,
            },
        }
