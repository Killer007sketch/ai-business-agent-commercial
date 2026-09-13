from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.proposal_agent import ProposalAgent, ProposalAgentError
from database.session import SessionLocal
from models.opportunity import Opportunity

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalGenerateRequest(BaseModel):
    opportunity_ids: list[int] = Field(min_length=1, max_length=5)
    dry_run: bool = True


def _row_to_agent_input(row: Opportunity) -> dict:
    try:
        requirements = json.loads(row.requirements_json or "[]")
    except json.JSONDecodeError:
        requirements = []

    if not isinstance(requirements, list):
        requirements = []

    return {
        "id": row.id,
        "source": row.source,
        "title": row.title,
        "source_url": row.source_url,
        "budget_text": row.budget_text,
        "budget_min_usd": row.budget_min_usd,
        "budget_max_usd": row.budget_max_usd,
        "problem": row.problem,
        "requirements": requirements,
        "filter_score": row.filter_score,
        "filter_status": row.filter_status,
    }


@router.post("/generate")
def generate_proposal(payload: ProposalGenerateRequest):
    # De-duplicate while preserving request order.
    requested_ids = list(dict.fromkeys(payload.opportunity_ids))

    db = SessionLocal()
    try:
        rows = db.query(Opportunity).filter(Opportunity.id.in_(requested_ids)).all()
        rows_by_id = {row.id: row for row in rows}
        missing = [item for item in requested_ids if item not in rows_by_id]
        if missing:
            raise HTTPException(status_code=404, detail=f"Unknown opportunity ids: {missing}")

        ordered_rows = [rows_by_id[item] for item in requested_ids]
        eligible = [
            row
            for row in ordered_rows
            if row.filter_status in {"shortlist", "review_later"}
        ]
        if not eligible:
            raise HTTPException(
                status_code=400,
                detail="No eligible opportunities. Only shortlist/review_later items may be sent to the Proposal Agent.",
            )

        opportunities = [_row_to_agent_input(row) for row in eligible]
        agent = ProposalAgent()

        try:
            if payload.dry_run:
                preview = agent.build_preview(opportunities)
                # Do not expose the full system instructions over the public API.
                preview.pop("instructions", None)
                return {"ok": True, "dry_run": True, **preview}

            result = agent.generate(opportunities)
            return {"ok": True, "dry_run": False, **result}
        except ProposalAgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()
