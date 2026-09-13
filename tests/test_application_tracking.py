from types import SimpleNamespace
from careerops.db.models import Application
from careerops.services.application_tracking import verification_state


def test_submitted_without_evidence_is_unverified():
    app=Application(job_id=1,status='submitted',answers={})
    assert verification_state(app)=='UNVERIFIED'


def test_submitted_with_confirmation_evidence_is_confirmed():
    app=Application(job_id=1,status='submitted',answers={'_submission_evidence':{'confirmed':True}})
    assert verification_state(app)=='CONFIRMED'


def test_review_is_not_claimed_as_submitted():
    app=Application(job_id=1,status='review',requires_human_review=True,answers={})
    assert verification_state(app)=='REVIEW'
