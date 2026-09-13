"""Notifications reach a phone, and a phone has no authorization (§19, §82).

A notification leaves this system's access control behind entirely. It is read
on a lock screen, by whoever is holding the handset, in a household that may
include the other party to a land dispute. So the strongest test here is not
that messages send -- it is that no template says anything worth overhearing.

The other property is that nothing in the workflow depends on a gateway. A
grievance must progress and a record must be approved whether or not an SMS
provider is reachable, and the in-app notification must survive either way.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.services import notification_service as notify_svc  # noqa: E402
from app.services.notification_service import (  # noqa: E402
    TEMPLATES,
    Delivery,
    Dispatcher,
    Msg91SmsProvider,
    NotificationError,
    NotificationProvider,
    RecordedProvider,
    WhatsAppCloudProvider,
    mask,
    normalise_phone,
)


class TestNoTemplateLeaksRecordContent:
    """The property that matters most, and the cheapest one to get wrong."""

    @pytest.mark.parametrize("key", sorted(TEMPLATES))
    def test_no_template_names_a_person_or_a_plot(self, key):
        template = TEMPLATES[key]
        text = (template.title + " " + template.body).lower()
        for leak in ("owner", "khasra", "khata", "area", "bigha", "hectare",
                     "aadhaar", "name of"):
            assert leak not in text, f"{key} mentions {leak!r}: {text}"

    @pytest.mark.parametrize("key", sorted(TEMPLATES))
    def test_variables_are_references_and_statuses_only(self, key):
        """A variable is the other way content leaks -- through the values."""
        allowed = {"reference", "status"}
        assert set(TEMPLATES[key].variables) <= allowed, TEMPLATES[key].variables

    @pytest.mark.parametrize("key", sorted(TEMPLATES))
    def test_every_template_tells_the_reader_to_sign_in(self, key):
        """The content lives behind authorization; the message is a pointer."""
        assert "sign in" in TEMPLATES[key].body.lower()


class TestRendering:
    def test_missing_variables_raise_rather_than_render_a_hole(self):
        with pytest.raises(NotificationError, match="reference"):
            TEMPLATES["record_approved"].render({})

    def test_extra_values_are_ignored_not_interpolated(self):
        """A caller passing a khasra number must not get it into the body."""
        title, body = TEMPLATES["record_approved"].render(
            {"reference": "DOC-1", "khasra_number": "142/2"}
        )
        assert "142/2" not in body and "142/2" not in title

    def test_the_reference_does_reach_the_body(self):
        _, body = TEMPLATES["record_approved"].render({"reference": "DOC-42"})
        assert "DOC-42" in body


class TestPhoneNormalisation:
    @pytest.mark.parametrize("raw", ["9876543210", "09876543210",
                                     "+91 98765 43210", "91-98765-43210"])
    def test_indian_numbers_all_reach_one_gateway_string(self, raw):
        assert normalise_phone(raw) == "919876543210"

    @pytest.mark.parametrize("raw", [None, "", "12", "abc", "1"])
    def test_unusable_numbers_are_none_not_guesses(self, raw):
        assert normalise_phone(raw) is None

    def test_masking_keeps_only_the_last_four_digits(self):
        assert mask("+919876543210") == "***3210"

    def test_masking_a_short_value_reveals_nothing(self):
        assert mask("12") == "***"


class TestProvidersRefuseUnregisteredTemplates:
    """Both regimes drop an unregistered message and report success."""

    def test_whatsapp_refuses_without_an_approved_template_name(self):
        provider = WhatsAppCloudProvider("token", "12345")
        template = TEMPLATES["record_approved"].__class__(
            key="x", variables=(), title="t", body="b", whatsapp_name=None
        )
        with pytest.raises(NotificationError, match="WhatsApp template name"):
            provider.send("919876543210", template, {})

    def test_msg91_refuses_without_a_dlt_template_id(self):
        """India: no dlt_te_id means the operator silently drops it."""
        provider = Msg91SmsProvider("key", "MRTIKA")
        with pytest.raises(NotificationError, match="DLT template ID"):
            provider.send("919876543210", TEMPLATES["record_approved"], {"reference": "X"})

    def test_a_placeholder_template_id_is_treated_as_absent(self):
        provider = Msg91SmsProvider("key", "MRTIKA")
        template = TEMPLATES["record_approved"].__class__(
            key="x", variables=(), title="t", body="b", dlt_template_id="CHANGEME"
        )
        with pytest.raises(NotificationError, match="DLT template ID"):
            provider.send("919876543210", template, {})

    def test_unconfigured_providers_report_unavailable(self):
        assert WhatsAppCloudProvider(None, None).available() is False
        assert Msg91SmsProvider(None, None).available() is False


class TestDispatcher:
    def test_with_no_gateway_the_attempt_is_still_recorded(self):
        recorder = RecordedProvider()
        delivery = Dispatcher(providers=[recorder]).deliver(
            "9876543210", TEMPLATES["record_approved"], {"reference": "DOC-1"}
        )
        assert delivery.delivered is False
        assert len(recorder.sent) == 1

    def test_a_missing_phone_number_is_not_an_error(self):
        delivery = Dispatcher(providers=[RecordedProvider()]).deliver(
            None, TEMPLATES["record_approved"], {"reference": "DOC-1"}
        )
        assert delivery.delivered is False
        assert "no usable phone number" in delivery.detail

    def test_a_failing_provider_falls_through_to_the_next(self):
        class Broken(NotificationProvider):
            name = "broken"

            def send(self, recipient, template, values):
                raise NotificationError("gateway on fire")

        class Working(NotificationProvider):
            name = "working"

            def send(self, recipient, template, values):
                return Delivery("sms", recipient, template.key, True)

        delivery = Dispatcher(providers=[Broken(), Working()]).deliver(
            "9876543210", TEMPLATES["record_approved"], {"reference": "DOC-1"}
        )
        assert delivery.delivered is True

    def test_every_provider_failing_returns_a_record_not_an_exception(self):
        class Broken(NotificationProvider):
            name = "broken"

            def send(self, recipient, template, values):
                raise NotificationError("gateway on fire")

        delivery = Dispatcher(providers=[Broken()]).deliver(
            "9876543210", TEMPLATES["record_approved"], {"reference": "DOC-1"}
        )
        assert delivery.delivered is False
        assert "gateway on fire" in delivery.detail

    def test_a_delivery_record_never_carries_a_full_phone_number(self):
        delivery = Delivery("sms", "919876543210", "record_approved", True)
        assert delivery.to_dict()["recipient"] == "***3210"
        assert "9876543210" not in str(delivery.to_dict())


class TestUnknownTemplate:
    def test_notify_refuses_a_template_that_does_not_exist(self, db_session=None):
        with pytest.raises(NotificationError, match="unknown notification template"):
            notify_svc.notify(
                session=None, user_id="u", template_key="nope", values={}
            )


class TestGrievanceTriggersANotification:
    def test_a_status_change_writes_an_in_app_notification(self, client, auth):
        """End to end through the real endpoint, with no gateway configured."""
        from demo_users import CITIZEN_A, TEHSILDAR

        filed = client.post(
            "/api/v1/grievances",
            headers=auth(CITIZEN_A),
            data={"issue_type": "INCORRECT_AREA",
                  "description": "Recorded area looks wrong."},
        )
        assert filed.status_code == 201, filed.text
        reference = filed.json()["grievance_id"]

        before = _notification_count(CITIZEN_A)
        response = client.post(
            f"/api/v1/grievances/{reference}/status",
            json={"status": "UNDER_REVIEW", "note": "looking into it"},
            headers=auth(TEHSILDAR),
        )
        assert response.status_code == 200, response.text
        assert _notification_count(CITIZEN_A) == before + 1


def _notification_count(email: str) -> int:
    from app.db import SessionLocal
    from app.models import Notification, User

    with SessionLocal() as session:
        user = session.query(User).filter(User.email == email).one_or_none()
        if user is None:
            return 0
        return session.query(Notification).filter(
            Notification.user_id == user.id
        ).count()
