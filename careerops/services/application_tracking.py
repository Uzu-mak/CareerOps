from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from careerops.db.models import Application


def get_submission_evidence(app: Application) -> dict:
    answers = app.answers or {}
    evidence = answers.get('_submission_evidence') or {}
    return evidence if isinstance(evidence, dict) else {}


def verification_state(app: Application) -> str:
    evidence = get_submission_evidence(app)
    if app.status == 'submitted' and evidence.get('confirmed') is True:
        return 'CONFIRMED'
    if app.status == 'submitted':
        return 'UNVERIFIED'
    if app.requires_human_review or app.status == 'review':
        return 'REVIEW'
    if app.status in {'prepared', 'planned'}:
        return 'NOT_SUBMITTED'
    return 'NOT_SUBMITTED'


def record_browser_result(db: Session, app: Application, result) -> Application:
    now = datetime.now(timezone.utc)
    evidence = {
        'confirmed': bool(result.submitted),
        'browser_status': result.status,
        'final_url': result.url,
        'confirmation_term': getattr(result, 'confirmation_term', None),
        'confirmation_excerpt': getattr(result, 'confirmation_excerpt', None),
        'screenshot_path': result.screenshot_path,
        'filled_fields': list(result.filled_fields or []),
        'uploaded_files': list(result.uploaded_files or []),
        'manual_fields': list(result.manual_fields or []),
        'verified_at': now.isoformat() if result.submitted else None,
        'verification_method': 'browser_confirmation_text' if result.submitted else None,
    }
    answers = dict(app.answers or {})
    answers['_submission_evidence'] = evidence
    if getattr(result, 'auto_answers', None):
        from sqlalchemy import select
        from careerops.db.models import ApplicationReviewAnswer
        for question, text in result.auto_answers.items():
            row = db.scalar(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id == app.id,
                                                                  ApplicationReviewAnswer.question == question))
            if row is None:
                row = ApplicationReviewAnswer(application_id=app.id, question=question)
                db.add(row)
            row.answer, row.resolved, row.category = text, True, 'auto_draft'
            row.notes = 'Written by CareerOps from your resume and evidence (auto-answer essays is on)'
    for label, detail in (getattr(result, 'manual_details', None) or {}).items():
        plan = dict(answers.get(label) or {})
        plan.update({'mode': plan.get('mode', 'REVIEW'), 'reason': detail.get('reason') or plan.get('reason'),
                     'field_type': detail.get('type'), 'options': detail.get('options') or []})
        answers[label] = plan
    answers['_optional_blank'] = getattr(result, 'optional_blank', None) or {}
    app.answers = answers

    if result.submitted:
        app.status = 'submitted'
        app.submitted_at = now
        term = getattr(result, 'confirmation_term', None) or 'application confirmation detected'
        app.confirmation = f'{term} | {result.url}'
        app.requires_human_review = False
        app.human_review_reasons = []
    else:
        app.status = 'review' if result.manual_fields else 'prepared'
        app.requires_human_review = bool(result.manual_fields)
        app.human_review_reasons = next_review_queue(app.human_review_reasons, answers, result)
        _reopen_answers_that_did_not_stick(db, app, result)

    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def next_review_queue(previous, answers: dict, result) -> list[str]:
    """What still needs you after a browser run.

    The run is the authority: whatever it filled is done and whatever it lists is open.
    Only when it stopped early (CAPTCHA, sign-in, an earlier page) do form questions from
    an earlier run that this run never reached stay on the list.
    """
    from careerops.core.ui_options import is_blocker
    now = list(dict.fromkeys(result.manual_fields or []))
    if not any(is_blocker(m) for m in now):
        return now
    filled = set(result.filled_fields or [])
    carried = [q for q in (previous or []) if not is_blocker(q) and q not in filled and q not in now
               and isinstance(answers.get(q), dict) and 'field_type' in answers[q]]   # seen on the real form
    return list(dict.fromkeys(now + carried))


def _reopen_answers_that_did_not_stick(db, app: Application, result) -> None:
    """You answered it, CareerOps typed it, but the form still shows it empty: say so instead of hiding it."""
    if not result.manual_fields:
        return
    from sqlalchemy import select
    from careerops.db.models import ApplicationReviewAnswer
    rows = db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id == app.id,
                                                            ApplicationReviewAnswer.question.in_(list(result.manual_fields)))).all()
    answers = dict(app.answers or {})
    for row in rows:
        if row.resolved and row.answer:
            row.resolved = False
            db.add(row)
            plan = dict(answers.get(row.question) or {})
            plan['reason'] = (f'CareerOps entered your answer "{row.answer[:80]}" but the form did not accept it. '
                              'Check it against the form\'s options and save again.')
            plan['not_accepted'] = True
            answers[row.question] = plan
    app.answers = answers


def submission_evidence_summary(app: Application) -> dict:
    evidence = get_submission_evidence(app)
    screenshot_path = evidence.get('screenshot_path')
    return {
        'state': verification_state(app),
        'confirmed': verification_state(app) == 'CONFIRMED',
        'confirmation': app.confirmation,
        'verification_method': evidence.get('verification_method'),
        'confirmation_term': evidence.get('confirmation_term'),
        'confirmation_excerpt': evidence.get('confirmation_excerpt'),
        'final_url': evidence.get('final_url'),
        'verified_at': evidence.get('verified_at'),
        'screenshot_available': bool(screenshot_path and Path(screenshot_path).exists()),
        'filled_fields': evidence.get('filled_fields', []),
        'uploaded_files': evidence.get('uploaded_files', []),
        'manual_fields': evidence.get('manual_fields', []),
    }
