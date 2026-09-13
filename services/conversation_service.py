from __future__ import annotations

from datetime import datetime
from typing import Any

from database.session import SessionLocal
from models.conversation import Conversation, ConversationMessage


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def get_or_create_conversation(
    contact_email: str,
    contact_name: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    normalized_email = _normalize_email(contact_email)
    if not normalized_email:
        return {"ok": False, "reason": "missing_contact_email"}

    db = SessionLocal()
    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.contact_email == normalized_email)
            .first()
        )

        if conversation:
            changed = False
            if contact_name and not conversation.contact_name:
                conversation.contact_name = contact_name.strip()
                changed = True
            if company_name and not conversation.company_name:
                conversation.company_name = company_name.strip()
                changed = True
            if changed:
                conversation.updated_at = datetime.utcnow()
                db.commit()

            return {
                "ok": True,
                "created": False,
                "conversation_id": conversation.id,
                "status": conversation.status,
            }

        conversation = Conversation(
            contact_email=normalized_email,
            contact_name=(contact_name or "").strip() or None,
            company_name=(company_name or "").strip() or None,
            status="active",
            human_required=False,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return {
            "ok": True,
            "created": True,
            "conversation_id": conversation.id,
            "status": conversation.status,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_conversation_message(
    conversation_id: int,
    direction: str,
    body: str,
    sender_email: str | None = None,
    recipient_email: str | None = None,
    subject: str | None = None,
    provider_message_id: str | None = None,
    provider_email_id: str | None = None,
    intent: str | None = None,
    risk_level: str | None = None,
    human_required: bool | None = None,
) -> dict[str, Any]:
    direction = str(direction or "").strip().lower()
    if direction not in {"inbound", "outbound"}:
        raise ValueError("direction must be 'inbound' or 'outbound'")

    db = SessionLocal()
    try:
        if provider_email_id:
            existing = (
                db.query(ConversationMessage)
                .filter(ConversationMessage.provider_email_id == provider_email_id)
                .first()
            )
            if existing:
                return {
                    "ok": True,
                    "created": False,
                    "reason": "duplicate",
                    "message_id": existing.id,
                    "conversation_id": existing.conversation_id,
                }

        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if conversation is None:
            raise ValueError("conversation_not_found")

        message = ConversationMessage(
            conversation_id=conversation_id,
            direction=direction,
            sender_email=(sender_email or "").strip() or None,
            recipient_email=(recipient_email or "").strip() or None,
            subject=(subject or "").strip() or None,
            body=str(body or ""),
            provider_message_id=(provider_message_id or "").strip() or None,
            provider_email_id=(provider_email_id or "").strip() or None,
            intent=(intent or "").strip() or None,
            risk_level=(risk_level or "").strip() or None,
            human_required=human_required,
        )
        db.add(message)

        conversation.updated_at = datetime.utcnow()
        if intent:
            conversation.last_intent = intent
        if risk_level:
            conversation.last_risk_level = risk_level
        if human_required is not None:
            conversation.human_required = bool(human_required)

        db.commit()
        db.refresh(message)

        return {
            "ok": True,
            "created": True,
            "message_id": message.id,
            "conversation_id": conversation_id,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_conversation_history(conversation_id: int, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    db = SessionLocal()
    try:
        records = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        records.reverse()
        return [
            {
                "id": row.id,
                "direction": row.direction,
                "sender_email": row.sender_email,
                "recipient_email": row.recipient_email,
                "subject": row.subject,
                "body": row.body,
                "provider_message_id": row.provider_message_id,
                "provider_email_id": row.provider_email_id,
                "intent": row.intent,
                "risk_level": row.risk_level,
                "human_required": row.human_required,
                "created_at": row.created_at.isoformat(),
            }
            for row in records
        ]
    finally:
        db.close()


def get_conversation_by_email(contact_email: str) -> dict[str, Any] | None:
    normalized_email = _normalize_email(contact_email)
    if not normalized_email:
        return None

    db = SessionLocal()
    try:
        row = (
            db.query(Conversation)
            .filter(Conversation.contact_email == normalized_email)
            .first()
        )
        if row is None:
            return None

        return {
            "id": row.id,
            "contact_email": row.contact_email,
            "contact_name": row.contact_name,
            "company_name": row.company_name,
            "status": row.status,
            "human_required": row.human_required,
            "last_intent": row.last_intent,
            "last_risk_level": row.last_risk_level,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
    finally:
        db.close()


def update_message_analysis(
    message_id: int,
    intent: str | None = None,
    risk_level: str | None = None,
    human_required: bool | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        message = db.query(ConversationMessage).filter(ConversationMessage.id == message_id).first()
        if message is None:
            raise ValueError("message_not_found")
        conversation = db.query(Conversation).filter(Conversation.id == message.conversation_id).first()
        if intent is not None:
            message.intent = str(intent).strip() or None
            if conversation:
                conversation.last_intent = message.intent
        if risk_level is not None:
            message.risk_level = str(risk_level).strip() or None
            if conversation:
                conversation.last_risk_level = message.risk_level
        if human_required is not None:
            message.human_required = bool(human_required)
            if conversation:
                conversation.human_required = bool(human_required)
        if conversation:
            conversation.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "message_id": message.id, "conversation_id": message.conversation_id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
