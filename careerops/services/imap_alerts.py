from __future__ import annotations
import imaplib
from email import policy
from email.parser import BytesParser
from sqlalchemy.orm import Session
from careerops.core.config import settings
from careerops.services.alert_inbox import store_alert_email, infer_provider


def imap_configured() -> bool:
    return bool(settings.job_alert_imap_host and settings.job_alert_imap_user and settings.job_alert_imap_password)


def poll_imap_alerts(db: Session, max_messages: int = 40) -> dict:
    """Import unseen LinkedIn/Indeed alert emails into CareerOps.

    Credentials come only from environment/secret storage; they are never stored in PostgreSQL.
    Messages are marked seen only after successful ingestion.
    """
    if not imap_configured(): return {'configured':False,'imported':0,'skipped':0,'errors':[]}
    out={'configured':True,'imported':0,'skipped':0,'errors':[]}
    client=None
    try:
        client=imaplib.IMAP4_SSL(settings.job_alert_imap_host,settings.job_alert_imap_port)
        client.login(settings.job_alert_imap_user,settings.job_alert_imap_password)
        client.select(settings.job_alert_imap_folder)
        status,data=client.search(None,'UNSEEN')
        if status!='OK': raise RuntimeError('IMAP search failed')
        ids=(data[0] or b'').split()[-max_messages:]
        for mid in ids:
            try:
                status,msg_data=client.fetch(mid,'(RFC822)')
                if status!='OK': raise RuntimeError('IMAP fetch failed')
                raw=next((part[1] for part in msg_data if isinstance(part,tuple) and len(part)>1),None)
                if not raw: continue
                msg=BytesParser(policy=policy.default).parsebytes(raw)
                sender=str(msg.get('From') or ''); subject=str(msg.get('Subject') or '')
                provider=infer_provider(sender,subject,'')
                if provider not in {'linkedin','indeed'}:
                    out['skipped']+=1; continue
                store_alert_email(db,raw_email=raw.decode('utf-8','replace'),provider=provider)
                client.store(mid,'+FLAGS','\\Seen'); out['imported']+=1
            except Exception as exc: out['errors'].append(str(exc))
        return out
    except Exception as exc:
        out['errors'].append(str(exc)); return out
    finally:
        try:
            if client: client.logout()
        except Exception: pass
