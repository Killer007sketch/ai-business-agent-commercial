from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from database.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    contact_email = Column(String(320), nullable=False, index=True)
    contact_name = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    human_required = Column(Boolean, nullable=False, default=False)
    last_intent = Column(String(100), nullable=True)
    last_risk_level = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("contact_email", name="uq_conversation_contact_email"),
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    direction = Column(String(20), nullable=False)
    sender_email = Column(String(320), nullable=True)
    recipient_email = Column(String(320), nullable=True)
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=False)
    provider_message_id = Column(String(255), nullable=True)
    provider_email_id = Column(String(255), nullable=True)
    intent = Column(String(100), nullable=True)
    risk_level = Column(String(50), nullable=True)
    human_required = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint(
            "provider_email_id",
            name="uq_conversation_message_provider_email_id",
        ),
    )
