import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database.session import SessionLocal
from models.opportunity import Opportunity
from services.opportunity_filter import score_opportunity

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class OpportunityCreate(BaseModel):
    source: str | None = None
    title: str = Field(min_length=1, max_length=1000)
    source_url: str | None = None
    budget_text: str | None = None
    budget_min_usd: int | None = None
    budget_max_usd: int | None = None
    problem: str | None = None
    requirements: list[str] = Field(default_factory=list)


@router.post("")
def create_opportunity(payload: OpportunityCreate):
    data = payload.model_dump()

    score, status, reasons = score_opportunity(data)

    db = SessionLocal()
    try:
        row = Opportunity(
            source=data.get("source"),
            title=data["title"],
            source_url=data.get("source_url"),
            budget_text=data.get("budget_text"),
            budget_min_usd=data.get("budget_min_usd"),
            budget_max_usd=data.get("budget_max_usd"),
            problem=data.get("problem"),
            requirements_json=json.dumps(
                data.get("requirements") or [],
                ensure_ascii=False,
            ),
            filter_score=score,
            filter_status=status,
            pipeline_status=(
                "shortlisted" if status == "shortlist" else "discovered"
            ),
        )

        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "ok": True,
            "opportunity_id": row.id,
            "filter_score": score,
            "filter_status": status,
            "filter_reasons": reasons,
            "pipeline_status": row.pipeline_status,
            "llm_calls": 0,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()


@router.get("")
def list_opportunities(limit: int = 20):
    limit = max(1, min(limit, 100))

    db = SessionLocal()
    try:
        rows = (
            db.query(Opportunity)
            .order_by(
                Opportunity.filter_score.desc(),
                Opportunity.id.desc(),
            )
            .limit(limit)
            .all()
        )

        return {
            "ok": True,
            "count": len(rows),
            "items": [
                {
                    "id": row.id,
                    "source": row.source,
                    "title": row.title,
                    "source_url": row.source_url,
                    "budget_text": row.budget_text,
                    "filter_score": row.filter_score,
                    "filter_status": row.filter_status,
                    "pipeline_status": row.pipeline_status,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
        }
    finally:
        db.close()
