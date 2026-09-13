from __future__ import annotations
import json
import boto3
from careerops.core.config import settings


def send_email(subject: str, text: str) -> bool:
    if not (settings.ses_from_email and settings.ses_to_email): return False
    ses=boto3.client('sesv2',region_name=settings.aws_region)
    ses.send_email(FromEmailAddress=settings.ses_from_email,Destination={'ToAddresses':[settings.ses_to_email]},Content={'Simple':{'Subject':{'Data':subject},'Body':{'Text':{'Data':text}}}})
    return True


def enqueue(queue_url: str, payload: dict):
    sqs=boto3.client('sqs',region_name=settings.aws_region)
    return sqs.send_message(QueueUrl=queue_url,MessageBody=json.dumps(payload))
