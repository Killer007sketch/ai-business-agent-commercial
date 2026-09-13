from __future__ import annotations

import json
import os
import re
from email.utils import parseaddr

from fastapi import APIRouter, HTTPException, Request

from agents.conversation_agent import ConversationAgent, ConversationAgentError
from services.conversation_service import (
    get_conversation_history,
    get_or_create_conversation,
    save_conversation_message,
    update_message_analysis,
)
from services.email_service import ResendEmailService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def extract_latest_reply_text(full_text: str) -> str:
    text = str(full_text or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    kept: list[str] = []
    separators = [
        r"^\s*On .+ wrote:\s*$",
        r"^\s*From:\s+.+$",
        r"^\s*Sent:\s+.+$",
        r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$",
        r"^\s*_{2,}\s*$",
    ]
    for line in text.split("\n"):
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in separators):
            break
        if line.strip().startswith(">"):
            break
        kept.append(line)
    return "\n".join(kept).strip() or text


def _verify_resend_webhook(secret: str, raw_body: bytes, headers: dict[str, str]) -> None:
    """Verify a Resend/Svix webhook without making svix a hard import-time dependency."""
    try:
        from svix.webhooks import Webhook, WebhookVerificationError
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="svix_dependency_not_installed",
        ) from exc

    try:
        Webhook(secret).verify(raw_body, headers)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail="invalid_webhook_signature") from exc


@router.post("/resend")
async def resend_webhook(request: Request):
    secret = os.getenv("RESEND_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="resend_webhook_not_configured")

    raw_body = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    _verify_resend_webhook(secret, raw_body, headers)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_webhook_payload") from exc

    if payload.get("type") != "email.received":
        return {"ok": True, "handled": False, "event_type": payload.get("type")}

    data = payload.get("data") or {}
    email_id = str(data.get("email_id") or "").strip()
    if not email_id:
        return {"ok": True, "handled": False, "reason": "missing_email_id"}

    email_service = ResendEmailService()
    received = email_service.fetch_received_email(email_id)
    if not received:
        return {"ok": True, "handled": False, "reason": "received_email_fetch_failed"}

    raw_from = str(data.get("from") or received.get("from") or "").strip()
    sender_name, parsed_email = parseaddr(raw_from)
    sender_email = (parsed_email or raw_from).strip().lower()
    if not sender_email:
        return {"ok": True, "handled": False, "reason": "missing_sender_email"}

    body = extract_latest_reply_text(received.get("text") or "")
    subject = str(data.get("subject") or received.get("subject") or "").strip()
    to_value = data.get("to") or received.get("to") or ""
    recipient = to_value[0] if isinstance(to_value, list) and to_value else str(to_value or "")

    conversation = get_or_create_conversation(sender_email, sender_name or None)
    if not conversation.get("ok"):
        return {"ok": True, "handled": False, "reason": conversation.get("reason")}
    conversation_id = int(conversation["conversation_id"])
    history = get_conversation_history(conversation_id, limit=12)

    saved = save_conversation_message(
        conversation_id=conversation_id,
        direction="inbound",
        sender_email=sender_email,
        recipient_email=recipient,
        subject=subject,
        body=body,
        provider_message_id=str(data.get("message_id") or "").strip() or None,
        provider_email_id=email_id,
    )
    if saved.get("created") is False:
        return {
            "ok": True,
            "handled": True,
            "duplicate": True,
            "conversation_id": conversation_id,
        }

    # Disabled by default: webhook ingestion itself costs zero OpenAI calls.
    if not _env_bool("EMAIL_ANALYZE_INBOUND", False):
        return {
            "ok": True,
            "handled": True,
            "analyzed": False,
            "conversation_id": conversation_id,
        }

    try:
        result = ConversationAgent().analyze_message(
            from_email=sender_email,
            subject=subject,
            body=body,
            contact_name=sender_name or None,
            conversation_history=history,
            dry_run=False,
        )
    except ConversationAgentError:
        return {
            "ok": True,
            "handled": True,
            "analyzed": False,
            "reason": "conversation_analysis_failed",
        }

    analysis = result.get("analysis") or {}
    update_message_analysis(
        message_id=int(saved["message_id"]),
        intent=analysis.get("intent"),
        risk_level=analysis.get("risk_level"),
        human_required=analysis.get("human_required"),
    )

    auto_reply = _env_bool("EMAIL_AUTO_REPLY", False)
    reply_draft = str(analysis.get("reply_draft") or "").strip()
    allowed = (
        auto_reply
        and analysis.get("risk_level") == "low"
        and analysis.get("human_required") is False
        and bool(reply_draft)
        and not sender_email.startswith(("no-reply@", "noreply@"))
    )
    if not allowed:
        return {
            "ok": True,
            "handled": True,
            "analyzed": True,
            "auto_replied": False,
            "conversation_id": conversation_id,
        }

    reply_subject = (
        subject
        if subject.lower().startswith("re:")
        else (f"Re: {subject}" if subject else "Re: Your message")
    )
    inbound_message_id = str(data.get("message_id") or "").strip() or None
    send_result = email_service.send_text_email(
        to_email=sender_email,
        subject=reply_subject,
        body=reply_draft,
        idempotency_key=f"inbound-auto-reply-{email_id}",
        in_reply_to=inbound_message_id,
        references=inbound_message_id,
    )
    if send_result.get("ok"):
        save_conversation_message(
            conversation_id=conversation_id,
            direction="outbound",
            sender_email=email_service.from_email,
            recipient_email=sender_email,
            subject=reply_subject,
            body=reply_draft,
            provider_message_id=send_result.get("provider_message_id"),
        )
    return {
        "ok": True,
        "handled": True,
        "analyzed": True,
        "auto_replied": bool(send_result.get("ok")),
        "conversation_id": conversation_id,
    }
