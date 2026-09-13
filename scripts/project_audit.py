from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
checks=[]

def expect(name, condition, detail=''):
    checks.append((name,bool(condition),detail))

def contains(rel,*needles):
    text=(ROOT/rel).read_text(encoding='utf-8')
    return all(n in text for n in needles)

required=[
 'careerops/main.py','careerops/api/routes.py','careerops/db/models.py','careerops/workers/discovery.py',
 'careerops/workers/application_worker.py','careerops/services/notifications.py','careerops/services/alert_inbox.py',
 'careerops/services/imap_alerts.py','careerops/sources/adzuna.py','careerops/sources/usajobs.py',
 'careerops/sources/company_career.py','careerops/agents/browser.py','careerops/agents/account.py',
 'careerops/templates/notifications.html','careerops/templates/journal.html','careerops/templates/applications.html',
 'infra/terraform/main.tf','FEATURE_MATRIX.md','START_HERE_WINDOWS.txt'
]
for rel in required: expect(f'file:{rel}',(ROOT/rel).exists())

expect('dashboard routes',contains('careerops/main.py',"'/profile'","'/journal'","'/applications'","'/notifications'"))
expect('source types',contains('careerops/api/routes.py','company_career','adzuna','usajobs','linkedin_alerts','indeed_alerts'))
expect('priority company seeds',contains('careerops/db/init.py','SpaceX','Microsoft','Amazon','Boeing','Meta','Salesforce','OpenAI','Palantir'))
expect('broad market adapters',contains('careerops/workers/discovery.py','AdzunaSource','USAJobsSource','CompanyCareerSource'))
expect('alert inbox',contains('careerops/workers/discovery.py','poll_imap_alerts','process_pending_alerts'))
expect('notifications channels',contains('careerops/services/notifications.py','ses','slack','discord','telegram'))
expect('cross-source dedupe',contains('careerops/services/ingest.py','_source_priority','_semantic_duplicate'))
expect('location+role gate',contains('careerops/services/search_policy.py','evaluate_job_location','evaluate_job_role','should_keep_discovered_job'))
expect('resume baseline',contains('careerops/db/models.py','baseline_resume_path','baseline_resume_text'))
expect('living journal evidence',contains('careerops/db/models.py','CareerJournalEntry','architecture_decisions','tradeoffs','time_spent_hours','metrics','lessons'))
expect('links',contains('careerops/db/models.py','linkedin_url','github_url','ProfileLink'))
expect('browser multi-step',contains('careerops/agents/browser.py','for _step in range(10)','Save and Continue','Submit Application'))
expect('browser sensitive boundary',contains('careerops/agents/browser.py','CAPTCHA','authentication/MFA','portal account password / email verification'))
expect('submission confirmation',contains('careerops/agents/browser.py','thank you for applying','application submitted','submission confirmation not detected'))
expect('application proof model',contains('careerops/services/application_tracking.py','CONFIRMED','UNVERIFIED'))
expect('autopilot gates',contains('careerops/services/autopilot.py','auto_apply_min_fit','max_auto_applications_per_day','baseline_resume_path'))
expect('application queue',contains('careerops/services/application_queue.py','APPLICATION_QUEUE_URL') or contains('careerops/services/application_queue.py','application_queue_url'))
expect('watchtower 15m',contains('docker-compose.yml','sleep 900'))
expect('ports',contains('docker-compose.yml','5433:5432','8001:8000','db:5432'))
expect('aws discovery queue',contains('infra/terraform/main.tf','aws_sqs_queue" "discovery','rate(15 minutes)'))
expect('aws browser worker',contains('infra/terraform/main.tf','browser_worker','application_worker'))
expect('aws security',contains('infra/terraform/main.tf','aws_secretsmanager_secret','aws_kms_key','storage_encrypted'))
expect('no old demo sidebar',not contains('careerops/templates/base.html','Local demo running'))

failed=[x for x in checks if not x[1]]
for name,ok,detail in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' - '+detail) if detail else ''}")
print(f'\nAUDIT: {len(checks)-len(failed)}/{len(checks)} checks passed')
if failed:
    sys.exit(1)
