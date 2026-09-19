"""Telling a citizen something happened, without telling everyone else (§19).

Two constraints shape this module more than any design preference.

**Neither channel lets you send free text.** WhatsApp requires a template
approved by Meta for any business-initiated message outside a 24-hour reply
window. India's DLT regime requires transactional SMS to carry a template ID
registered with the telecom operators, or the message is dropped in transit.
So the unit of sending here is a TEMPLATE plus variables, never a string. A
`send(phone, "your record was approved")` API would work in development and
fail silently in production, which is the worst of both.

Email and push are further channels, sent IN ADDITION to the phone chain, not
as fallbacks from it: someone with a phone and a registered app gets both.

**A notification is delivered to a phone, not to a session.** It leaves the
system's authorization behind entirely -- it will be read on a lock screen, by
whoever is holding the handset. So no template carries record content. They
carry the fact that something changed and a reason to log in. "Your record
KHASRA 142/2 now lists Ram Prasad Singh as owner" is a disclosure to anyone who
picks up the phone; "a record you follow was updated" is not.

Providers are interchangeable and the absence of one is not an error (§82): with
no credentials configured the recorded provider logs the attempt and the
in-app notification is still written, so nothing in the workflow depends on an
SMS gateway being reachable.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import CitizenProfile, Notification, User

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    pass


@dataclass(frozen=True)
class Template:
    """One approved message shape.

    `whatsapp_name` is the template registered with Meta; `dlt_template_id` is
    the one registered on the Indian DLT portal. Both are per-deployment
    identifiers, so they are configuration, not constants -- the defaults here
    are placeholders and a provider refuses to send on a placeholder.
    """

    key: str
    variables: tuple[str, ...]
    #: The in-app title and body. `{}`-formatted from the variables.
    title: str
    body: str
    whatsapp_name: str | None = None
    dlt_template_id: str | None = None

    def render(self, values: dict) -> tuple[str, str]:
        missing = [v for v in self.variables if v not in values]
        if missing:
            raise NotificationError(
                f"template {self.key} needs {missing} and did not get them"
            )
        safe = {k: values[k] for k in self.variables}
        return self.title.format(**safe), self.body.format(**safe)


#: Every template the system may send. Adding one is a deliberate act: it also
#: has to be registered with Meta and on the DLT portal before it will deliver.
#:
#: Read every body below as if it were on a lock screen in a shared household.
#: None of them name a person, an owner, a khasra number or an area.
TEMPLATES: dict[str, Template] = {
    "record_approved": Template(
        key="record_approved",
        variables=("reference",),
        title="A record you follow was approved",
        body=(
            "Reference {reference} has completed verification and approval. "
            "Sign in to Mrittika AI to view it."
        ),
        whatsapp_name="mrittika_record_approved",
    ),
    "grievance_update": Template(
        key="grievance_update",
        variables=("reference", "status"),
        title="Your grievance was updated",
        body=(
            "Grievance {reference} is now {status}. Sign in to Mrittika AI for "
            "details."
        ),
        whatsapp_name="mrittika_grievance_update",
    ),
    "rescan_required": Template(
        key="rescan_required",
        variables=("reference",),
        title="A document needs rescanning",
        body=(
            "Document {reference} did not pass the quality check and needs to "
            "be scanned again. Sign in to Mrittika AI to see why."
        ),
        whatsapp_name="mrittika_rescan_required",
    ),
}

#: Values that mean "nobody configured this". A provider that finds one refuses
#: rather than sending, because a message on an unregistered template is
#: accepted by the API and then dropped by the operator -- a delivery failure
#: that looks like a success.
PLACEHOLDERS = frozenset({"", "changeme", "change_me", "your_template_id", "todo"})


@dataclass
class Delivery:
    channel: str
    recipient: str
    template: str
    delivered: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            # Never log a full phone number.
            "recipient": mask(self.recipient),
            "template": self.template,
            "delivered": self.delivered,
            "detail": self.detail,
        }


def mask(recipient: str) -> str:
    """Last four digits only, for logs and audit records."""
    digits = re.sub(r"\D", "", recipient or "")
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def normalise_phone(phone: str | None, default_country: str = "91") -> str | None:
    """E.164 without the plus, or None.

    Indian numbers are stored locally in several shapes -- 9876543210,
    09876543210, +91 98765 43210. All three are the same subscriber and all
    three must reach the same gateway string.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    digits = digits.lstrip("0")
    if len(digits) == 10:
        digits = default_country + digits
    return digits if 11 <= len(digits) <= 15 else None


class NotificationProvider(ABC):
    name = "abstract"

    @abstractmethod
    def send(self, recipient: str, template: Template, values: dict) -> Delivery:
        ...

    def available(self) -> bool:
        return True


class RecordedProvider(NotificationProvider):
    """The default. Records the attempt and sends nothing.

    Not a no-op: the in-app notification is still written by `notify`, and the
    attempt is visible. A demo deployment with no gateway credentials behaves
    identically to a real one from every other part of the system's point of
    view, which is what keeps the trigger logic testable (§82).
    """

    name = "recorded"

    def __init__(self) -> None:
        self.sent: list[Delivery] = []

    def send(self, recipient: str, template: Template, values: dict) -> Delivery:
        delivery = Delivery(
            channel="recorded", recipient=recipient, template=template.key,
            delivered=False,
            detail="no gateway configured; in-app notification written instead",
        )
        self.sent.append(delivery)
        logger.info("notification (not sent): %s", delivery.to_dict())
        return delivery


class WhatsAppCloudProvider(NotificationProvider):
    """WhatsApp Business Cloud API.

    POST https://graph.facebook.com/{version}/{phone_number_id}/messages with a
    bearer token. Business-initiated messages must use a template approved by
    Meta; free-form text is only allowed inside a 24-hour window after the user
    writes first, which never happens here.
    """

    name = "whatsapp"

    def __init__(
        self,
        access_token: str | None,
        phone_number_id: str | None,
        *,
        api_version: str = "v23.0",
        language: str = "en",
        timeout: float = 10.0,
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.language = language
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def send(self, recipient: str, template: Template, values: dict) -> Delivery:
        if not self.available():
            raise NotificationError("WhatsApp credentials are not configured")
        if not template.whatsapp_name or template.whatsapp_name.lower() in PLACEHOLDERS:
            raise NotificationError(
                f"template {template.key} has no approved WhatsApp template name; "
                "Meta rejects business-initiated messages without one"
            )

        import httpx

        url = (f"https://graph.facebook.com/{self.api_version}/"
               f"{self.phone_number_id}/messages")
        parameters = [
            {"type": "text", "text": str(values[name])} for name in template.variables
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template.whatsapp_name,
                "language": {"code": self.language},
                "components": [{"type": "body", "parameters": parameters}],
            },
        }

        try:
            response = httpx.post(
                url, json=payload, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        except Exception as exc:
            raise NotificationError(f"WhatsApp request failed: {exc}") from exc

        if response.status_code >= 300:
            raise NotificationError(
                f"WhatsApp rejected the message ({response.status_code}): "
                f"{response.text[:200]}"
            )
        return Delivery(
            channel="whatsapp", recipient=recipient, template=template.key,
            delivered=True, detail=f"HTTP {response.status_code}",
        )


class Msg91SmsProvider(NotificationProvider):
    """MSG91, an Indian SMS gateway.

    Transactional SMS in India is governed by TRAI's DLT regime: the message
    must carry a template ID registered against a principal entity, and the
    body must match the registered text. A message sent without a valid
    `dlt_te_id` is accepted by the API and silently dropped by the operator, so
    this refuses to send without one rather than reporting a false success.
    """

    name = "msg91"

    def __init__(
        self,
        auth_key: str | None,
        sender_id: str | None,
        *,
        pe_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.auth_key = auth_key
        self.sender_id = sender_id
        self.pe_id = pe_id
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.auth_key and self.sender_id)

    def send(self, recipient: str, template: Template, values: dict) -> Delivery:
        if not self.available():
            raise NotificationError("MSG91 credentials are not configured")
        dlt = template.dlt_template_id
        if not dlt or dlt.lower() in PLACEHOLDERS:
            raise NotificationError(
                f"template {template.key} has no DLT template ID. An Indian "
                "transactional SMS without one is accepted by the API and "
                "dropped by the operator -- a failure that looks like success"
            )

        import httpx

        payload = {
            "template_id": dlt,
            "sender": self.sender_id,
            "short_url": "0",
            "recipients": [{"mobiles": recipient, **{
                k: str(values[k]) for k in template.variables
            }}],
        }
        if self.pe_id:
            payload["PE_ID"] = self.pe_id

        try:
            response = httpx.post(
                "https://control.msg91.com/api/v5/flow/",
                json=payload, timeout=self.timeout,
                headers={"authkey": self.auth_key, "Content-Type": "application/json"},
            )
        except Exception as exc:
            raise NotificationError(f"MSG91 request failed: {exc}") from exc

        if response.status_code >= 300:
            raise NotificationError(
                f"MSG91 rejected the message ({response.status_code}): "
                f"{response.text[:200]}"
            )
        return Delivery(
            channel="sms", recipient=recipient, template=template.key,
            delivered=True, detail=f"HTTP {response.status_code}",
        )


class EmailProvider:
    """Email over SMTP, with the standard library.

    Sends the same lock-screen-safe title and body as the in-app notification
    -- an inbox is read on shared screens too.
    """

    name = "email"

    def __init__(self, host: str | None, sender: str | None, *, port: int = 587,
                 username: str | None = None, password: str | None = None,
                 starttls: bool = True, timeout: float = 10.0) -> None:
        self.host, self.sender, self.port = host, sender, port
        self.username, self.password = username, password
        self.starttls, self.timeout = starttls, timeout

    def available(self) -> bool:
        return bool(self.host and self.sender)

    def send(self, address: str, template: Template, values: dict) -> Delivery:
        import smtplib
        from email.message import EmailMessage

        title, body = template.render(values)
        message = EmailMessage()
        message["Subject"], message["From"], message["To"] = title, self.sender, address
        message.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                if self.starttls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password or "")
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationError(f"SMTP delivery failed: {exc}") from exc
        return Delivery(channel="email", recipient=address, template=template.key,
                        delivered=True, detail="accepted by SMTP server")


class ExpoPushProvider:
    """Push to the mobile app through Expo's push service.

    Expo answers 200 even for a token it rejects, with the verdict in the body,
    so the body is read -- a 200 alone is not a delivery.
    """

    name = "push"
    URL = "https://exp.host/--/api/v2/push/send"

    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        self.access_token, self.timeout = access_token, timeout

    def send(self, token: str, template: Template, values: dict,
             link: str | None = None) -> Delivery:
        import httpx

        title, body = template.render(values)
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            response = httpx.post(self.URL, headers=headers, timeout=self.timeout, json={
                "to": token, "title": title, "body": body, "data": {"link": link},
            })
            result = response.json().get("data") or {}
        except Exception as exc:
            raise NotificationError(f"Expo push request failed: {exc}") from exc
        if response.status_code >= 300 or result.get("status") != "ok":
            reason = result.get("message") or response.text[:200]
            raise NotificationError(f"Expo rejected the push: {reason}")
        return Delivery(channel="push", recipient=token, template=template.key,
                        delivered=True, detail=f"ticket {result.get('id', '')}")


def extra_channels(user: User | None, template: Template, values: dict,
                   link: str | None = None, settings=None) -> list[Delivery]:
    """Email and push for this user, where configured. Never raises: a failed
    channel is a Delivery with delivered=False, like the phone chain's."""
    if user is None:
        return []
    if settings is None:
        from app.config.settings import get_settings

        settings = get_settings()

    deliveries = []
    email = EmailProvider(
        settings.smtp_host, settings.smtp_sender, port=settings.smtp_port,
        username=settings.smtp_username, password=settings.smtp_password,
        starttls=settings.smtp_starttls,
    )
    attempts = []
    if email.available():
        attempts.append(("email", user.email, lambda: email.send(user.email, template, values)))
    if settings.expo_push_enabled and user.push_token:
        push = ExpoPushProvider(settings.expo_access_token)
        attempts.append(("push", user.push_token,
                         lambda: push.send(user.push_token, template, values, link)))
    for channel, recipient, attempt in attempts:
        try:
            deliveries.append(attempt())
        except NotificationError as exc:
            logger.warning("notification channel %s failed: %s", channel, exc)
            deliveries.append(Delivery(channel=channel, recipient=recipient,
                                       template=template.key, delivered=False, detail=str(exc)))
    return deliveries


@dataclass
class Dispatcher:
    """Tries each provider in turn; the in-app record is written regardless."""

    providers: list[NotificationProvider] = dc_field(default_factory=list)

    def deliver(self, recipient: str | None, template: Template, values: dict) -> Delivery:
        number = normalise_phone(recipient)
        if number is None:
            return Delivery(
                channel="none", recipient=recipient or "", template=template.key,
                delivered=False, detail="no usable phone number on file",
            )

        errors = []
        for provider in self.providers:
            if not provider.available():
                continue
            try:
                return provider.send(number, template, values)
            except NotificationError as exc:
                errors.append(f"{provider.name}: {exc}")
                logger.warning("notification provider %s failed: %s", provider.name, exc)

        return Delivery(
            channel="none", recipient=number, template=template.key, delivered=False,
            detail="; ".join(errors) or "no provider available",
        )


def build_default_dispatcher(settings=None) -> Dispatcher:
    """The dispatcher the app uses, from configuration.

    RecordedProvider is always last, so an unconfigured deployment still
    produces a delivery record instead of an exception.
    """
    if settings is None:
        from app.config.settings import get_settings

        settings = get_settings()

    providers: list[NotificationProvider] = []
    whatsapp = WhatsAppCloudProvider(
        getattr(settings, "whatsapp_access_token", None),
        getattr(settings, "whatsapp_phone_number_id", None),
    )
    if whatsapp.available():
        providers.append(whatsapp)

    sms = Msg91SmsProvider(
        getattr(settings, "msg91_auth_key", None),
        getattr(settings, "msg91_sender_id", None),
        pe_id=getattr(settings, "msg91_pe_id", None),
    )
    if sms.available():
        providers.append(sms)

    providers.append(RecordedProvider())
    return Dispatcher(providers=providers)


def notify(
    session: Session,
    *,
    user_id: str,
    template_key: str,
    values: dict,
    link: str | None = None,
    dispatcher: Dispatcher | None = None,
) -> tuple[Notification, Delivery]:
    """Record an in-app notification and attempt external delivery.

    The in-app row is written FIRST and unconditionally. A citizen who never
    receives the SMS must still find the update when they sign in; making the
    durable record depend on a gateway would lose it exactly when the gateway
    is down.
    """
    template = TEMPLATES.get(template_key)
    if template is None:
        raise NotificationError(f"unknown notification template {template_key!r}")

    title, body = template.render(values)
    notification = Notification(
        user_id=user_id, title=title, body=body, link=link, is_read=False
    )
    session.add(notification)
    session.flush()

    profile = session.query(CitizenProfile).filter(
        CitizenProfile.user_id == user_id
    ).one_or_none()
    user = session.get(User, user_id)
    phone = profile.phone if profile else None

    dispatcher = dispatcher or build_default_dispatcher()
    delivery = dispatcher.deliver(phone, template, values)
    others = extra_channels(user, template, values, link)
    logger.info(
        "notified user=%s template=%s delivered=%s others=%s at=%s",
        user.email if user else user_id, template_key, delivery.delivered,
        [(d.channel, d.delivered) for d in others], datetime.now(UTC).isoformat(),
    )
    return notification, delivery


__all__ = [
    "PLACEHOLDERS", "TEMPLATES", "Delivery", "Dispatcher", "EmailProvider",
    "ExpoPushProvider", "Msg91SmsProvider", "extra_channels",
    "NotificationError", "NotificationProvider", "RecordedProvider", "Template",
    "WhatsAppCloudProvider", "build_default_dispatcher", "mask",
    "normalise_phone", "notify",
]
