# CareerOps v3.0.1 Architecture

## End-to-end flow

```text
                         CANDIDATE PROFILE
             resume + links + legal facts + journal
                                  |
                                  v
                          CandidateEvidence
                                  |
                                  +--------------------------+
                                  |                          |
                                  v                          |
DISCOVERY ---------------------------------------------------+
  |                                                          |
  +-- Greenhouse / Lever / Ashby                             |
  +-- public company-career watcher                          |
  +-- Adzuna broad market                                    |
  +-- USAJOBS                                                |
  +-- LinkedIn / Indeed alert-email inbox                    |
  |                                                          |
  v                                                          |
Normalize -> fingerprint -> cross-source dedupe               |
  |                                                          |
  v                                                          |
Location/work-arrangement gate -> role-family gate            |
  |                                                          |
  v                                                          |
JD Analysis -> Policy Engine -> Fit Agent <-------------------+
  |
  +--> dashboard recommendation + notification
  |
  +--> optional Autopilot gate
         |
         v
Evidence retrieval -> tailored resume -> cover letter -> Q&A
         |
         v
Portal Account Plan -> Playwright Browser Agent
         |
         +--> multi-step safe field/file fill
         +--> account/sign-in gate detected -> human takeover
         +--> CAPTCHA/MFA/sensitive question -> human review
         |
         v
Final submit
         |
         v
Employer acknowledgement detector
         |
   +-----+--------------------+
   |                          |
confirmed                 not confirmed
   |                          |
SUBMITTED/CONFIRMED       REVIEW/UNVERIFIED
   |                          |
   +------------+-------------+
                v
 Applications CRM -> outcome tracking -> notifications/reports
```

## Discovery architecture

The Watchtower is intentionally multi-channel rather than pretending one scraper can cover the entire job market.

```text
Direct ATS feeds        Broad market        Alert inbox         Priority companies
Greenhouse              Adzuna              LinkedIn email      SpaceX
Lever                   USAJOBS             Indeed email        Microsoft
Ashby                                                           Amazon
                                                                Boeing
                                                                Meta
                                                                Salesforce
     \___________________________  ______________________________/
                                 \/
                         normalize + dedupe
                                 |
                       location + role filter
                                 |
                           fit + notify
```

`company_career` first uses normal public HTTP + schema.org `JobPosting`. For JavaScript-rendered public pages it can use Chromium to inspect the rendered page and a bounded number of same-host/known-ATS links. It never logs in or bypasses anti-bot controls.

## Authority and evidence model

PostgreSQL is authoritative for candidate profile, user-verified legal facts, evidence, jobs, analyses, applications, source state, notifications and runtime settings.

```text
Master resume -----------\
Structured evidence ------+--> CandidateEvidence --> retrieval
Build Journal -----------/
```

Only user-entered/verified metrics may be presented as measured impact. Generated text is advisory and cannot overwrite verified legal facts.

## Application state and proof

```text
planned -> prepared -> review -> submitted -> interview -> offer
                           \-> rejected / withdrawn
```

Submission proof is separate from workflow status:

```text
Browser clicks final Submit
          |
          v
Employer response page
          |
    +-----+--------------------+
    |                          |
acknowledgement detected     none / blocked
    |                          |
phrase + URL + timestamp      REVIEW
+ screenshot                  never counted confirmed
    |
CONFIRMED
```

A manually marked `submitted` application without browser evidence remains `UNVERIFIED`.

## Human-review boundary

CareerOps can persist exact application answers the user explicitly approves. It must not infer sensitive legal/demographic facts. Authentication challenges are a takeover boundary: raw portal passwords are not stored in PostgreSQL, CAPTCHA/MFA is not bypassed, and email/OAuth ownership verification remains the user's action.

## Local runtime

```text
Docker Compose
  db          PostgreSQL
  app         FastAPI + UI + local browser actions
  watchtower  15-minute discovery loop
```

The laptop must remain awake with Docker running for local continuous monitoring.

## AWS runtime

```text
EventBridge Scheduler (15m)
         |
         v
Discovery SQS -> Discovery ECS/Fargate worker -> providers
         |                                     |
         |                                     v
         |                                  RDS/S3
         |
         +--> Application SQS -> Browser ECS/Fargate worker
                                      |
                                      v
                                    RDS/S3

ALB -> FastAPI ECS service -> RDS / S3 / Bedrock / SES

Secrets Manager + KMS
CloudWatch logs
DLQs for discovery/application failures
```

The API, discovery worker, and browser worker are independently deployable. PostgreSQL remains the canonical store; S3 stores artifacts/raw evidence. AWS deployment requires user-authorized account access and should add ACM/HTTPS/custom domain before production use.
