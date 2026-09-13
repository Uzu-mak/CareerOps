from __future__ import annotations
import json, os, time
import boto3
from sqlalchemy import select
from careerops.core.config import settings
from careerops.db.session import SessionLocal
from careerops.db.models import CandidateProfile, JobPosting
from careerops.services.autopilot import attempt_autopilot_application


def main():
    queue_url=os.getenv('APPLICATION_QUEUE_URL') or settings.application_queue_url
    if not queue_url: raise SystemExit('APPLICATION_QUEUE_URL is required')
    sqs=boto3.client('sqs',region_name=settings.aws_region)
    while True:
        resp=sqs.receive_message(QueueUrl=queue_url,MaxNumberOfMessages=2,WaitTimeSeconds=20,VisibilityTimeout=600)
        for msg in resp.get('Messages',[]):
            try:
                body=json.loads(msg['Body'])
                if body.get('type')=='autopilot_apply':
                    db=SessionLocal()
                    try:
                        profile=db.scalar(select(CandidateProfile).limit(1)); job=db.get(JobPosting,int(body['job_id']))
                        if profile and job: attempt_autopilot_application(db,profile,job,allow_enqueue=False)
                    finally: db.close()
                sqs.delete_message(QueueUrl=queue_url,ReceiptHandle=msg['ReceiptHandle'])
            except Exception as exc:
                print('application worker error',exc,flush=True)
        time.sleep(1)

if __name__=='__main__': main()
