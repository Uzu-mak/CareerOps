from __future__ import annotations
import json
import boto3
from careerops.core.config import settings


def enqueue_application(job_id: int) -> bool:
    if not settings.application_queue_url: return False
    sqs=boto3.client('sqs',region_name=settings.aws_region)
    sqs.send_message(QueueUrl=settings.application_queue_url,MessageBody=json.dumps({'type':'autopilot_apply','job_id':job_id}))
    return True
