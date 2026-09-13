from __future__ import annotations
import asyncio, json, os, time
import boto3
from careerops.core.config import settings
from careerops.workers.discovery import scan_enabled_sources
from careerops.workers.report import run as run_daily_report


def main():
    queue_url=os.getenv('QUEUE_URL')
    if not queue_url: raise SystemExit('QUEUE_URL is required')
    sqs=boto3.client('sqs',region_name=settings.aws_region)
    while True:
        resp=sqs.receive_message(QueueUrl=queue_url,MaxNumberOfMessages=5,WaitTimeSeconds=20,VisibilityTimeout=180)
        for msg in resp.get('Messages',[]):
            try:
                body=json.loads(msg['Body'])
                if body.get('type')=='scan_enabled_sources': asyncio.run(scan_enabled_sources())
                elif body.get('type')=='daily_report': run_daily_report()
                sqs.delete_message(QueueUrl=queue_url,ReceiptHandle=msg['ReceiptHandle'])
            except Exception as exc:
                print('worker error',exc,flush=True)
        time.sleep(1)

if __name__=='__main__': main()
