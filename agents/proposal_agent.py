from __future__ import annotations

import json
import os
from typing import Any

from config.business_config import get_business_config

try:
    from openai import OpenAI
except ImportError:  # Allows zero-cost dry runs/tests without OpenAI installed.
    OpenAI = None  # type: ignore[assignment]


class ProposalAgentError(RuntimeError):
    """Raised when the Proposal Agent cannot safely produce a result."""


class ProposalAgent:
    """
    Low-cost proposal generator for already-filtered opportunities.

    Cost controls:
    - no web search
    - accepts only a small configured shortlist
    - exactly one OpenAI Responses API call when generate() is executed
    - build_preview() makes zero OpenAI calls
    """

    ALLOWED_DECISIONS = {"APPLY", "BUILD_DEMO_FIRST", "SKIP"}

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or get_business_config()
        proposal_cfg = self.config["proposal_agent"]

        self.business = self.config["business"]
        self.offer = self.config["offer"]
        self.scope = self.config["scope"]
        self.proposal_cfg = proposal_cfg

        self.model = os.getenv("PROPOSAL_AGENT_MODEL", proposal_cfg["model"])
        self.max_opportunities = int(proposal_cfg["max_opportunities"])
        self.max_problem_chars = int(proposal_cfg["max_problem_chars"])
        self.max_requirements = int(proposal_cfg["max_requirements"])
        self.min_words = int(proposal_cfg["proposal_min_words"])
        self.max_words = int(proposal_cfg["proposal_max_words"])

        self.client = client
        if self.client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key and OpenAI is not None:
                self.client = OpenAI(api_key=api_key)

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    def _compact_opportunities(self, opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []

        for item in opportunities[: self.max_opportunities]:
            opportunity_id = item.get("id", item.get("opportunity_id", item.get("job_id")))
            title = self._clean_text(item.get("title"))

            if opportunity_id is None or not title:
                continue

            requirements = item.get("requirements") or []
            if not isinstance(requirements, list):
                requirements = []

            compact.append(
                {
                    "opportunity_id": opportunity_id,
                    "source": self._clean_text(item.get("source")) or None,
                    "title": title,
                    "source_url": self._clean_text(item.get("source_url")) or None,
                    "budget_text": self._clean_text(item.get("budget_text")) or None,
                    "budget_min_usd": item.get("budget_min_usd"),
                    "budget_max_usd": item.get("budget_max_usd"),
                    "problem": self._clean_text(item.get("problem"))[: self.max_problem_chars],
                    "requirements": [
                        self._clean_text(value)
                        for value in requirements[: self.max_requirements]
                        if self._clean_text(value)
                    ],
                    "filter_score": item.get("filter_score"),
                }
            )

        if not compact:
            raise ProposalAgentError("No valid opportunities supplied")

        return compact

    def _instructions(self) -> str:
        approved_scope = "\n".join(f"- {item}" for item in self.scope["approved"])
        excluded_scope = "\n".join(f"- {item}" for item in self.scope["excluded"])

        return f"""
You are a Proposal Agent for {self.business['name']}.

Choose exactly ONE opportunity that can realistically be delivered within the
configured business scope. Prefer clear scope, low external dependency,
reasonable budget, and work that can be implemented reliably.

Configured offer: {self.offer['name']}.
Approved capabilities:
{approved_scope}

Excluded or unapproved scope:
{excluded_scope}

You have no browsing tools. Use only the opportunity data supplied in the input.
Never invent experience, clients, portfolio items, credentials, results,
technologies, deadlines, prices, or facts that are not supported by the input.
Do not claim that work has already been completed.

Return JSON only with exactly this shape:
{{
  "selected_opportunity_id": 0,
  "source_url": null,
  "decision": "APPLY" | "BUILD_DEMO_FIRST" | "SKIP",
  "why": "...",
  "delivery_plan": ["..."],
  "questions_for_client": ["..."],
  "proposal": "...",
  "estimated_autonomy_percent": 0,
  "human_needed_for": ["..."]
}}

Client-facing proposal rules:
- Do not mention autonomous agents, internal architecture, internal risk scoring,
  or how the business is operated.
- Focus on the client's desired result and a simple implementation approach.
- Keep the proposal approximately {self.min_words}-{self.max_words} words.
- Ask at most 2 important questions.
- Do not promise a delivery deadline unless the listing provides enough
  information to support that promise.
- Do not make guarantees or false claims.
""".strip()

    def build_preview(self, opportunities: list[dict[str, Any]]) -> dict[str, Any]:
        """Prepare the exact compact input without calling OpenAI."""
        compact = self._compact_opportunities(opportunities)
        return {
            "model": self.model,
            "input_opportunity_count": len(compact),
            "web_search_used": False,
            "llm_calls": 0,
            "instructions": self._instructions(),
            "input": compact,
        }

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProposalAgentError("Model returned invalid JSON") from exc

        if not isinstance(result, dict):
            raise ProposalAgentError("Model result must be a JSON object")
        return result

    def _validate_result(
        self,
        result: dict[str, Any],
        compact: list[dict[str, Any]],
    ) -> dict[str, Any]:
        allowed_ids = {item["opportunity_id"] for item in compact}
        selected_id = result.get("selected_opportunity_id")
        if selected_id not in allowed_ids:
            raise ProposalAgentError("Model returned an unknown opportunity id")

        decision = self._clean_text(result.get("decision")).upper()
        if decision not in self.ALLOWED_DECISIONS:
            raise ProposalAgentError("Model returned an invalid decision")
        result["decision"] = decision

        selected = next(item for item in compact if item["opportunity_id"] == selected_id)
        returned_url = result.get("source_url")
        expected_url = selected.get("source_url")
        if returned_url not in (None, "", expected_url):
            raise ProposalAgentError("Model returned a source URL outside the selected opportunity")
        result["source_url"] = expected_url

        for list_field in ("delivery_plan", "questions_for_client", "human_needed_for"):
            value = result.get(list_field, [])
            if not isinstance(value, list):
                raise ProposalAgentError(f"'{list_field}' must be a list")
            result[list_field] = [self._clean_text(item) for item in value if self._clean_text(item)]

        result["questions_for_client"] = result["questions_for_client"][:2]
        result["why"] = self._clean_text(result.get("why"))
        result["proposal"] = self._clean_text(result.get("proposal"))

        try:
            autonomy = int(result.get("estimated_autonomy_percent", 0))
        except (TypeError, ValueError):
            autonomy = 0
        result["estimated_autonomy_percent"] = max(0, min(100, autonomy))

        if decision != "SKIP" and not result["proposal"]:
            raise ProposalAgentError("Model returned an empty proposal")

        return result

    def generate(self, opportunities: list[dict[str, Any]]) -> dict[str, Any]:
        """Make exactly one OpenAI call and return a validated proposal decision."""
        compact = self._compact_opportunities(opportunities)

        if self.client is None:
            raise ProposalAgentError(
                "OPENAI_API_KEY is not configured. Use build_preview() for a zero-cost test."
            )

        response = self.client.responses.create(
            model=self.model,
            instructions=self._instructions(),
            input=json.dumps(compact, ensure_ascii=False),
        )

        raw = self._clean_text(getattr(response, "output_text", ""))
        if not raw:
            raise ProposalAgentError("Model returned an empty response")

        result = self._validate_result(self._extract_json(raw), compact)

        return {
            "model": self.model,
            "input_opportunity_count": len(compact),
            "web_search_used": False,
            "llm_calls": 1,
            "result": result,
        }
