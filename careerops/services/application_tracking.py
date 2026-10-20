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
        # Questions stay until answered; status blockers from an earlier run are replaced by this run's.
        from careerops.core.ui_options import is_blocker
        kept = [r for r in (app.human_review_reasons or []) if not is_blocker(r)]
        app.human_review_reasons = list(dict.fromkeys(kept + list(result.manual_fields or [])))

    db.add(app)
    db.commit()
    db.refresh(app)
    return app


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
