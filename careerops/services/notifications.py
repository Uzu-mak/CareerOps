from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
import httpx
import boto3
from careerops.core.config import settings
from careerops.db.models import NotificationPreference, NotificationEvent, JobPosting, Application


def get_notification_preferences(db: Session) -> NotificationPreference:
    row=db.scalar(select(NotificationPreference).limit(1))
    if row is None:
        row=NotificationPreference(email_to=settings.ses_to_email, slack_webhook_url=settings.slack_webhook_url,
            discord_webhook_url=settings.discord_webhook_url, telegram_bot_token=settings.telegram_bot_token,
            telegram_chat_id=settings.telegram_chat_id)
        db.add(row); db.commit(); db.refresh(row)
    return row


def _channels(pref: NotificationPreference) -> list[str]:
    out=['in_app']
    if pref.email_enabled and pref.email_to: out.append('email')
    if pref.slack_enabled and (pref.slack_webhook_url or settings.slack_webhook_url): out.append('slack')
    if pref.discord_enabled and (pref.discord_webhook_url or settings.discord_webhook_url): out.append('discord')
    if pref.telegram_enabled and (pref.telegram_bot_token or settings.telegram_bot_token) and (pref.telegram_chat_id or settings.telegram_chat_id): out.append('telegram')
    return out


def should_notify(pref: NotificationPreference, event_type: str, fit_score: float | None=None) -> bool:
    if not pref.enabled: return False
    flags={
        'new_match':pref.notify_new_match,'high_fit':pref.notify_high_fit,'human_review':pref.notify_human_review,
        'submitted':pref.notify_submitted,'failed':pref.notify_failed,
    }
    if not flags.get(event_type, True): return False
    if event_type in {'new_match','high_fit'} and fit_score is not None and fit_score < pref.minimum_fit_score: return False
    return True


def emit_notification(db: Session, event_type: str, title: str, message: str, *, job: JobPosting|None=None,
                      application: Application|None=None, fit_score: float|None=None, priority: str|None=None) -> NotificationEvent | None:
    pref=get_notification_preferences(db)
    if not should_notify(pref,event_type,fit_score): return None
    event=NotificationEvent(event_type=event_type,title=title,message=message,job_id=job.id if job else None,
        application_id=application.id if application else None,fit_score=fit_score,priority=priority,
        channels_requested=_channels(pref),status='created')
    db.add(event); db.commit(); db.refresh(event)
    results={'in_app':{'ok':True}}
    for ch in [x for x in event.channels_requested if x!='in_app']:
        try:
            if ch=='email': _send_email(pref,title,message); results[ch]={'ok':True}
            elif ch=='slack': _send_webhook(pref.slack_webhook_url or settings.slack_webhook_url, {'text':f'*{title}*\n{message}'}); results[ch]={'ok':True}
            elif ch=='discord': _send_webhook(pref.discord_webhook_url or settings.discord_webhook_url, {'content':f'**{title}**\n{message}'}); results[ch]={'ok':True}
            elif ch=='telegram': _send_telegram(pref,title,message); results[ch]={'ok':True}
        except Exception as exc:
            results[ch]={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
    event.delivery_results=results
    event.sent_at=datetime.now(timezone.utc)
    event.status='sent' if all(v.get('ok') for v in results.values()) else 'partial'
    db.add(event); db.commit(); db.refresh(event)
    return event


def notify_job_match(db: Session, job: JobPosting, analysis) -> NotificationEvent | None:
    event_type='high_fit' if analysis.fit_score >= get_notification_preferences(db).urgent_fit_score else 'new_match'
    title=f'CareerOps — {analysis.priority} opportunity: {job.title}'
    message=f'{job.company} · {job.location or "Location not listed"}\nFit: {analysis.fit_score:.0f}% · Decision: {analysis.recommended_action}\n{job.application_url or job.canonical_url or "No application URL"}'
    return emit_notification(db,event_type,title,message,job=job,fit_score=analysis.fit_score,priority=analysis.priority)


def notify_application_event(db: Session, event_type: str, application: Application, job: JobPosting, detail: str=''):
    title_map={'submitted':'CareerOps — application confirmed','human_review':'CareerOps — action required','failed':'CareerOps — application failed'}
    title=f"{title_map.get(event_type,'CareerOps application update')}: {job.company} — {job.title}"
    return emit_notification(db,event_type,title,detail or application.status,job=job,application=application)


def _send_email(pref: NotificationPreference, subject: str, body: str):
    if not settings.ses_from_email: raise RuntimeError('SES_FROM_EMAIL not configured')
    client=boto3.client('ses',region_name=settings.aws_region)
    client.send_email(Source=settings.ses_from_email,Destination={'ToAddresses':[pref.email_to]},Message={'Subject':{'Data':subject},'Body':{'Text':{'Data':body}}})


def _send_webhook(url: str|None, payload: dict):
    if not url: raise RuntimeError('webhook not configured')
    with httpx.Client(timeout=15,follow_redirects=True) as client:
        r=client.post(url,json=payload); r.raise_for_status()


def _send_telegram(pref: NotificationPreference, title: str, body: str):
    token=pref.telegram_bot_token or settings.telegram_bot_token; chat_id=pref.telegram_chat_id or settings.telegram_chat_id
    if not token or not chat_id: raise RuntimeError('Telegram not configured')
    with httpx.Client(timeout=15) as client:
        r=client.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat_id,'text':f'{title}\n\n{body}'}); r.raise_for_status()
