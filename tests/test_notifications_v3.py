from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from careerops.db.base import Base
from careerops.db.models import NotificationPreference, NotificationEvent, JobPosting
from careerops.services.notifications import should_notify, emit_notification, get_notification_preferences


def test_notification_thresholds():
    p=NotificationPreference(enabled=True,minimum_fit_score=75,urgent_fit_score=90,notify_new_match=True)
    assert not should_notify(p,'new_match',74)
    assert should_notify(p,'new_match',75)
    p.enabled=False
    assert not should_notify(p,'new_match',99)


def test_in_app_notification_persists_without_external_channels():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        pref=get_notification_preferences(db)
        pref.email_enabled=False; pref.slack_enabled=False; pref.discord_enabled=False; pref.telegram_enabled=False
        db.add(pref);db.commit()
        event=emit_notification(db,'test','Hello','CareerOps notification test')
        assert event is not None
        assert event.delivery_results['in_app']['ok'] is True
        assert db.scalar(select(NotificationEvent)).title=='Hello'
