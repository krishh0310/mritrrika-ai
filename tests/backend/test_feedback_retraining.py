"""Verifier corrections reach the extractor's training data (§30, §67).

    correct -> review (accept/reject) -> export -> train

Each link is tested on a real correction made through the verification
service. The case that matters most is the AI reading the WRONG block: the
exported page must teach the model the block that carries the corrected value,
not the one the AI chose, or the "learning" would reinforce the mistake.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from demo_users import DEO, TEHSILDAR, VERIFIER
from staged_documents import (
    Field,
    delete,
    extraction,
    finish_verification,
    principal,
    stage,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

LABEL = (80, 150, 260, 184)
RIGHT = (300, 150, 400, 184)     # '142/2', beside the label
WRONG = (300, 260, 380, 294)     # '999', a stray number lower down

BLOCKS = [
    ("ग्राम", (80, 100, 260, 134)),
    ("रामपुर", (300, 100, 460, 134)),
    ("खसरा सं", LABEL),
    ("142/2", RIGHT),
    ("999", WRONG),
]
FIELDS = [
    Field("VILLAGE", "रामपुर", 0.95, (300, 100, 460, 134)),
    # Confident and wrong: the most valuable kind of correction.
    Field("KHASRA", "999", 0.93, WRONG),
]


@pytest.fixture
def session(client):
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


@pytest.fixture
def corrected(session):
    """A document mid-verification with KHASRA corrected from 999 to 142/2."""
    from app.services import verification_service

    document = stage(session, FIELDS, BLOCKS)
    verification_service.correct_field(
        session, extraction(session, document, "KHASRA").id, "142/2",
        principal=principal(session, VERIFIER),
    )
    yield document
    delete(session, document)


def feedback_for(session, document):
    from app.models import AiFeedback, FieldCorrection
    from sqlalchemy import select

    return session.execute(
        select(AiFeedback)
        .join(FieldCorrection, FieldCorrection.id == AiFeedback.correction_id)
        .where(FieldCorrection.document_id == document.id)
    ).scalar_one()


def page_for(session, document):
    from app.services import feedback_service

    return next(
        (p for p in feedback_service.training_pages(session)
         if p["document_id"] == document.external_id),
        None,
    )


class TestReview:
    def test_a_correction_arrives_unreviewed(self, session, corrected):
        row = feedback_for(session, corrected)
        assert row.reviewed is False
        assert row.review_decision is None
        assert row.selection_reason == "CONFIDENT_BUT_WRONG"

    def test_accepting_counts_towards_readiness(self, client, auth, session, corrected):
        from app.services import feedback_service

        before = feedback_service.readiness(session).accepted
        row = feedback_for(session, corrected)
        response = client.post(
            f"/api/v1/ai/feedback/{row.id}/review",
            json={"decision": "accepted", "note": "stray number read as khasra"},
            headers=auth(TEHSILDAR),
        )
        assert response.status_code == 200, response.text
        assert response.json()["review_decision"] == "ACCEPTED"
        assert response.json()["readiness"]["accepted"] == before + 1

    def test_rejecting_does_not(self, client, auth, session, corrected):
        from app.services import feedback_service

        before = feedback_service.readiness(session).accepted
        row = feedback_for(session, corrected)
        client.post(f"/api/v1/ai/feedback/{row.id}/review",
                    json={"decision": "REJECTED"}, headers=auth(TEHSILDAR))
        session.expire_all()
        assert feedback_service.readiness(session).accepted == before
        assert feedback_for(session, corrected).reviewed is True

    def test_a_review_is_audited(self, client, auth, session, corrected):
        from app.models import AuditEvent

        row = feedback_for(session, corrected)
        client.post(f"/api/v1/ai/feedback/{row.id}/review",
                    json={"decision": "ACCEPTED"}, headers=auth(TEHSILDAR))
        event = session.query(AuditEvent).filter(
            AuditEvent.action == "ai.feedback_reviewed", AuditEvent.entity_id == row.id
        ).one()
        assert event.after_state["decision"] == "ACCEPTED"

    def test_an_unknown_decision_is_refused(self, client, auth, session, corrected):
        row = feedback_for(session, corrected)
        response = client.post(f"/api/v1/ai/feedback/{row.id}/review",
                               json={"decision": "maybe"}, headers=auth(TEHSILDAR))
        assert response.status_code == 422

    def test_an_unknown_row_is_not_found(self, client, auth):
        response = client.post("/api/v1/ai/feedback/nope/review",
                               json={"decision": "ACCEPTED"}, headers=auth(TEHSILDAR))
        assert response.status_code == 404

    @pytest.mark.parametrize("email", [DEO, VERIFIER])
    def test_only_the_tehsildar_decides_what_the_model_learns(
        self, client, auth, session, corrected, email
    ):
        row = feedback_for(session, corrected)
        response = client.post(f"/api/v1/ai/feedback/{row.id}/review",
                               json={"decision": "ACCEPTED"}, headers=auth(email))
        assert response.status_code == 403


class TestExport:
    def _accept(self, session, document):
        from app.services import feedback_service

        feedback_service.review(
            session, feedback_for(session, document).id,
            decision="ACCEPTED", principal=principal(session, TEHSILDAR),
        )

    def test_a_page_still_under_verification_is_not_exported(self, session, corrected):
        """Its other fields are unjudged; labelling them would teach the model
        to agree with its own guesses."""
        self._accept(session, corrected)
        assert page_for(session, corrected) is None

    def test_a_rejected_correction_is_not_exported(self, session, corrected):
        from app.services import feedback_service

        feedback_service.review(
            session, feedback_for(session, corrected).id,
            decision="REJECTED", principal=principal(session, TEHSILDAR),
        )
        finish_verification(session, corrected, VERIFIER)
        assert page_for(session, corrected) is None

    def test_a_finished_accepted_page_is_exported_with_every_field(
        self, session, corrected
    ):
        self._accept(session, corrected)
        finish_verification(session, corrected, VERIFIER)
        page = page_for(session, corrected)

        assert page is not None
        fields = {f["field"]: f for f in page["fields"]}
        assert fields["KHASRA"]["value"] == "142/2"
        assert fields["KHASRA"]["ai_value"] == "999"
        assert fields["KHASRA"]["corrected"] is True
        assert fields["VILLAGE"]["corrected"] is False
        assert len(page["blocks"]) == len(BLOCKS)

    def test_the_label_follows_the_corrected_value_not_the_ai_box(
        self, session, corrected
    ):
        from collections import Counter

        from build_extraction_dataset import LABELS
        from export_feedback_dataset import to_training_row

        self._accept(session, corrected)
        finish_verification(session, corrected, VERIFIER)
        sources = Counter()
        row = to_training_row(page_for(session, corrected), "test", sources)

        labelled = {word: LABELS[label] for word, label in zip(row["words"], row["labels"],
                                                               strict=True)}
        assert labelled["142/2"] == "B-KHASRA"
        assert labelled["999"] == "O", "the AI's wrong block must not be taught"
        assert labelled["रामपुर"] == "B-VILLAGE"
        assert sources["corrected-value-block"] == 1
        assert row["source"] == "verifier-feedback"
        assert row["feedback_ids"] == [feedback_for(session, corrected).id]

    def test_rows_are_stamped_with_their_first_dataset_only(self, session, corrected):
        from app.services import feedback_service

        self._accept(session, corrected)
        row_id = feedback_for(session, corrected).id
        assert feedback_service.mark_included(session, [row_id], "run-1") == 1
        assert feedback_service.mark_included(session, [row_id], "run-2") == 0
        session.expire_all()
        assert feedback_for(session, corrected).included_in_dataset == "run-1"
