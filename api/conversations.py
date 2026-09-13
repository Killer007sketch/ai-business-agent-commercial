from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.conversation_agent import ConversationAgent, ConversationAgentError
from services.conversation_service import (
    get_conversation_by_email,
    get_conversation_history,
    get_or_create_conversation,
    save_conversation_message,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationAnalyzeRequest(BaseModel):
    from_email: str = Field(min_length=3, max_length=320)
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=20000)
    contact_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    provider_message_id: str | None = Field(default=None, max_length=255)
    provider_email_id: str | None = Field(default=None, max_length=255)
    dry_run: bool = True
    persist: bool = True


class OutboundMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    subject: str = Field(default="", max_length=500)
    recipient_email: str | None = Field(default=None, max_length=320)
    provider_message_id: str | None = Field(default=None, max_length=255)
    provider_email_id: str | None = Field(default=None, max_length=255)


@router.post("/analyze")
def analyze_conversation(payload: ConversationAnalyzeRequest):
    if not payload.subject.strip() and not payload.body.strip():
        raise HTTPException(status_code=400, detail="subject and body cannot both be empty")

    conversation = get_or_create_conversation(
        contact_email=str(payload.from_email),
        contact_name=payload.contact_name,
        company_name=payload.company_name,
    )
    if not conversation.get("ok"):
        raise HTTPException(status_code=400, detail=conversation.get("reason"))

    conversation_id = int(conversation["conversation_id"])
    history = get_conversation_history(conversation_id, limit=20)

    agent = ConversationAgent()
    try:
        result = agent.analyze_message(
            from_email=str(payload.from_email),
            subject=payload.subject,
            body=payload.body,
            contact_name=payload.contact_name,
            company_name=payload.company_name,
            conversation_history=history,
            dry_run=payload.dry_run,
        )
    except ConversationAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analysis = result["analysis"]

    saved = None
    if payload.persist:
        try:
            saved = save_conversation_message(
                conversation_id=conversation_id,
                direction="inbound",
                sender_email=str(payload.from_email),
                subject=payload.subject,
                body=payload.body,
                provider_message_id=payload.provider_message_id,
                provider_email_id=payload.provider_email_id,
                intent=analysis.get("intent"),
                risk_level=analysis.get("risk_level"),
                human_required=analysis.get("human_required"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        **result,
        "conversation_id": conversation_id,
        "conversation_created": conversation.get("created", False),
        "message_saved": saved,
    }


@router.post("/{conversation_id}/messages/outbound")
def save_outbound_message(conversation_id: int, payload: OutboundMessageRequest):
    try:
        saved = save_conversation_message(
            conversation_id=conversation_id,
            direction="outbound",
            recipient_email=(str(payload.recipient_email) if payload.recipient_email else None),
            subject=payload.subject,
            body=payload.body,
            provider_message_id=payload.provider_message_id,
            provider_email_id=payload.provider_email_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return saved


@router.get("/by-email/{contact_email}")
def conversation_by_email(contact_email: str, history_limit: int = 20):
    conversation = get_conversation_by_email(contact_email)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    history = get_conversation_history(conversation["id"], limit=history_limit)
    return {"ok": True, "conversation": conversation, "history": history}
