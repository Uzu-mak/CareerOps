from __future__ import annotations
import json
from careerops.db.session import SessionLocal
from careerops.agents.reporting import build_daily_report
from careerops.services.aws import send_email


def run():
    db=SessionLocal()
    try:
        report=build_daily_report(db); text=json.dumps(report,indent=2)
        return {'sent':send_email('CareerOps Daily Report',text),'report':report}
    finally: db.close()

if __name__=='__main__': print(run())
