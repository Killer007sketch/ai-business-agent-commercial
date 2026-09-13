from __future__ import annotations

import os
import re
from typing import Any

import requests

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def valid_email(value: str | None) -> bool:
    value = str(value or "").strip()
    return bool(value and len(value) <= 320 and EMAIL_PATTERN.fullmatch(value))


def safe_header(value: str | None, max_length: int) -> bool:
    value = str(value or "")
    return bool(value.strip()) and len(value) <= max_length and "\r" not in value and "\n" not in value


class ResendEmailService:
    """Small Resend adapter. No LLM calls are made by this service."""

    api_base = "https://api.resend.com"

    def __init__(
        self,
        api_key: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("RESEND_API_KEY")
        self.from_email = (from_email or os.getenv("EMAIL_FROM_ADDRESS") or "").strip().lower()
        self.from_name = (from_name or os.getenv("EMAIL_FROM_NAME") or "AI Business Agent").strip()

    def configured(self) -> bool:
        return bool(self.api_key and valid_email(self.from_email))

    def send_text_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        idempotency_key: str,
        reply_to: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        to_email = str(to_email or "").strip().lower()
        subject = str(subject or "").strip()
        body = str(body or "").strip()
        idempotency_key = str(idempotency_key or "").strip()

        if not self.configured():
            return {"ok": False, "reason": "email_provider_not_configured"}
        if not valid_email(to_email):
            return {"ok": False, "reason": "invalid_recipient_email"}
        if not safe_header(subject, 300):
            return {"ok": False, "reason": "invalid_subject"}
        if not body or len(body) > 50000:
            return {"ok": False, "reason": "invalid_body"}
        if not idempotency_key or len(idempotency_key) > 256:
            return {"ok": False, "reason": "invalid_idempotency_key"}
        if reply_to and not valid_email(reply_to):
            return {"ok": False, "reason": "invalid_reply_to"}

        custom_headers: dict[str, str] = {}
        for name, value in (("In-Reply-To", in_reply_to), ("References", references)):
            if value:
                if not safe_header(value, 2000):
                    return {"ok": False, "reason": f"invalid_{name.lower().replace('-', '_')}"}
                custom_headers[name] = str(value).strip()

        payload: dict[str, Any] = {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        if reply_to:
            payload["reply_to"] = reply_to.strip().lower()
        if custom_headers:
            payload["headers"] = custom_headers

        try:
            response = requests.post(
                f"{self.api_base}/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"ok": False, "reason": "provider_request_failed", "error": str(exc)}

        try:
            data = response.json()
        except ValueError:
            data = {"raw_response": response.text}
        if not response.ok:
            return {"ok": False, "reason": "provider_api_error", "status_code": response.status_code, "response": data}
        if not data.get("id"):
            return {"ok": False, "reason": "missing_provider_message_id", "response": data}
        return {"ok": True, "provider_message_id": data["id"], "status_code": response.status_code}

    def fetch_received_email(self, email_id: str) -> dict[str, Any] | None:
        email_id = str(email_id or "").strip()
        if not self.api_key or not email_id:
            return None
        try:
            response = requests.get(
                f"{self.api_base}/emails/receiving/{email_id}",
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                timeout=20,
            )
        except requests.RequestException:
            return None
        if not response.ok:
            return None
        try:
            return response.json()
        except ValueError:
            return None
