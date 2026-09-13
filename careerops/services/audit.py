from __future__ import annotations
import time
from contextlib import contextmanager
from sqlalchemy.orm import Session
from careerops.db.models import AgentRun


@contextmanager
def agent_run(db: Session, name: str, job_id: int | None = None, application_id: int | None = None, provider: str = 'local', input_summary: str | None = None):
    started = time.perf_counter()
    run = AgentRun(agent_name=name, job_id=job_id, application_id=application_id, model_provider=provider, input_summary=input_summary)
    try:
        yield run
        run.status = 'success'
    except Exception as exc:
        run.status = 'error'
        run.error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        db.add(run)
        db.commit()
