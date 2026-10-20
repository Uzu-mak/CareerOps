"""Answers the browser agent may reuse: this application's approved ones, and the bank."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerops.agents.apply_plan import bankable
from careerops.db.models import Application, ApplicationReviewAnswer, ProfileLink

APPROVED_MODES = {'AUTO_PROFILE', 'AUTO_RULE', 'AUTO_VERIFIED', 'USER_VERIFIED'}


def approved_answers(db: Session, app: Application) -> dict[str, str]:
    """Answers the user approved (or that came from verified profile rules) for this application."""
    out: dict[str, str] = {}
    for question, plan in (app.answers or {}).items():
        if not isinstance(plan, dict) or question.startswith('_'):
            continue
        answer = plan.get('user_answer') or plan.get('answer')
        if answer is not None and (plan.get('user_resolved') or plan.get('mode') in APPROVED_MODES):
            out[question] = str(answer)
    rows = db.scalars(select(ApplicationReviewAnswer).where(
        ApplicationReviewAnswer.application_id == app.id, ApplicationReviewAnswer.resolved == True)).all()  # noqa: E712
    for row in rows:
        if row.answer:
            out[row.question] = row.answer
    return out


def answer_bank(db: Session, exclude_application_id: int | None = None) -> dict[str, str]:
    """Resolved answers from earlier applications, newest first, for non-sensitive questions only.

    "How did you hear about us?" or "Are you willing to work hybrid?" answered once
    can be reused; EEO, criminal-history, attestation, citizenship, clearance,
    salary and work-authorization answers never leave the application they were given for.
    """
    rows = db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.resolved == True)  # noqa: E712
                      .order_by(ApplicationReviewAnswer.updated_at.desc())).all()
    bank: dict[str, str] = {}
    for row in rows:
        if row.application_id == exclude_application_id or not row.answer:
            continue
        if row.question not in bank and bankable(row.question):
            bank[row.question] = row.answer
    return bank


def application_links(db: Session, profile_id: int) -> list[dict]:
    return [
        {'label': x.label, 'url': x.url, 'link_type': x.link_type, 'include_in_applications': x.include_in_applications}
        for x in db.scalars(select(ProfileLink).where(ProfileLink.profile_id == profile_id)).all()
    ]
