from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from database.base import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)

    source = Column(String(100), nullable=True)
    title = Column(String(1000), nullable=False)
    source_url = Column(String(1500), nullable=True)

    budget_text = Column(String(500), nullable=True)
    budget_min_usd = Column(Integer, nullable=True)
    budget_max_usd = Column(Integer, nullable=True)

    problem = Column(Text, nullable=True)
    requirements_json = Column(Text, nullable=True)

    filter_score = Column(Integer, nullable=False, default=0)
    filter_status = Column(String(50), nullable=False, default="new")
    pipeline_status = Column(String(50), nullable=False, default="discovered")

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
