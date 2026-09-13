from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from careerops.db.models import CandidateProfile, JobPosting, Application, RuntimeSettings, ProfileLink, ApplicationReviewAnswer
from careerops.agents.orchestrator import prepare_application, latest_analysis
from careerops.agents.browser import run_generic_browser, detect_portal
from careerops.services.audit import agent_run
from careerops.services.application_tracking import record_browser_result


def get_runtime_settings(db: Session) -> RuntimeSettings:
    row = db.scalar(select(RuntimeSettings).limit(1))
    if not row:
        row = RuntimeSettings(auto_apply_enabled=False, auto_apply_min_fit=90, max_auto_applications_per_day=5)
        db.add(row); db.commit(); db.refresh(row)
    return row


def _submitted_today(db: Session) -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count(Application.id)).where(Application.submitted_at >= start)) or 0


def eligible_for_autopilot(db: Session, profile: CandidateProfile, job: JobPosting) -> tuple[bool, str]:
    cfg = get_runtime_settings(db)
    if not cfg.auto_apply_enabled:
        return False, 'auto-apply disabled'
    if not profile.baseline_resume_path:
        return False, 'master resume not uploaded'
    if not profile.legal_answers_verified_at:
        return False, 'legal/work-authorization answers not verified'
    analysis = latest_analysis(db, job.id)
    if not analysis:
        return False, 'job not analyzed'
    if analysis.hard_filter_status == 'FAIL':
        return False, 'hard constraint failed'
    if analysis.recommended_action != 'APPLY':
        return False, f'recommendation is {analysis.recommended_action}'
    if analysis.fit_score < cfg.auto_apply_min_fit:
        return False, f'fit {analysis.fit_score:.0f}% below threshold {cfg.auto_apply_min_fit}%'
    if _submitted_today(db) >= cfg.max_auto_applications_per_day:
        return False, 'daily auto-apply cap reached'
    if not (job.application_url or job.canonical_url):
        return False, 'no application URL'
    return True, 'eligible'


def attempt_autopilot_application(db: Session, profile: CandidateProfile, job: JobPosting, allow_enqueue: bool=True) -> dict:
    ok, reason = eligible_for_autopilot(db, profile, job)
    if not ok:
        return {'attempted': False, 'submitted': False, 'reason': reason}
    if allow_enqueue:
        try:
            from careerops.services.application_queue import enqueue_application
            if enqueue_application(job.id):
                return {'attempted': True, 'submitted': False, 'queued': True, 'reason': 'queued for browser worker'}
        except Exception as exc:
            # Queue failure falls back to direct processing so a transient SQS problem does not silently drop the application.
            reason=f'queue fallback: {exc}'
    target = job.application_url or job.canonical_url
    package = prepare_application(db, job)
    app = package['application']
    app.portal = detect_portal(target)
    app.mode = 'AUTO'
    db.add(app); db.commit(); db.refresh(app)
    try:
        with agent_run(db, 'AutopilotBrowserAgent', job_id=job.id, application_id=app.id, input_summary=f'{app.portal} unattended-safe attempt') as run:
            extra_links=[{'label':x.label,'url':x.url,'link_type':x.link_type,'include_in_applications':x.include_in_applications} for x in db.scalars(select(ProfileLink).where(ProfileLink.profile_id==profile.id)).all()]
            approved_review_answers={}
            for q,plan in (app.answers or {}).items():
                if not isinstance(plan,dict): continue
                answer=plan.get('user_answer') or plan.get('answer')
                if answer is not None and (plan.get('user_resolved') or plan.get('mode') in {'AUTO_PROFILE','AUTO_RULE','AUTO_VERIFIED','USER_VERIFIED'}):
                    approved_review_answers[q]=str(answer)
            for x in db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==app.id,ApplicationReviewAnswer.resolved==True)).all():
                if x.answer: approved_review_answers[x.question]=x.answer
            result = run_generic_browser(profile, job, app, target, resume_path=package['resume'].file_path, cover_letter_path=package['cover_letter'].file_path, submit=True, extra_links=extra_links, approved_review_answers=approved_review_answers)
            run.output_summary = f'{result.status}; {len(result.filled_fields)} fields; {len(result.manual_fields)} review items'
    except Exception as exc:
        app.status = 'review'; app.requires_human_review = True
        app.human_review_reasons = sorted(set((app.human_review_reasons or []) + [f'browser error: {type(exc).__name__}']))
        db.add(app); db.commit()
        try:
            from careerops.services.notifications import notify_application_event
            notify_application_event(db,'failed',app,job,str(exc))
        except Exception:
            pass
        return {'attempted': True, 'submitted': False, 'reason': str(exc), 'application_id': app.id}
    record_browser_result(db, app, result)
    return {'attempted': True, 'submitted': bool(result.submitted), 'status': result.status, 'reason': result.message, 'application_id': app.id, 'manual_fields': result.manual_fields}
