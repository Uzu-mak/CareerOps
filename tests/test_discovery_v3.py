from careerops.sources.adzuna import AdzunaSource
from careerops.sources.usajobs import USAJobsSource
from careerops.sources.company_career import CompanyCareerSource
from careerops.services.alert_inbox import infer_provider, extract_alert_urls, extract_alert_candidates
from careerops.db.init import starter_source_specs


def test_adzuna_result_mapping():
    row={
        'id':'abc123','title':'AI Engineer','description':'Build AI systems','redirect_url':'https://example.com/job',
        'salary_min':120000,'salary_max':150000,'company':{'display_name':'Example AI'},
        'location':{'display_name':'Seattle, WA'},'created':'2026-09-12T10:00:00Z'
    }
    x=AdzunaSource.map_result(row)
    assert x['source']=='adzuna'
    assert x['company']=='Example AI'
    assert x['location']=='Seattle, WA'
    assert x['salary_min']==120000
    assert x['application_url']=='https://example.com/job'


def test_usajobs_result_mapping():
    item={'MatchedObjectId':'42','MatchedObjectDescriptor':{
        'PositionID':'ABC-42','PositionTitle':'IT Specialist (AI)','PositionURI':'https://www.usajobs.gov/job/42',
        'ApplyURI':['https://www.usajobs.gov/apply/42'],'OrganizationName':'Example Agency',
        'PositionLocation':[{'LocationName':'Seattle, Washington'}],
        'PositionRemuneration':[{'MinimumRange':'100000','MaximumRange':'145000'}],
        'PublicationStartDate':'2026-09-12T00:00:00Z','ApplicationCloseDate':'2026-09-30T00:00:00Z',
        'UserArea':{'Details':{'JobSummary':'AI engineering','MajorDuties':'Build systems'}}
    }}
    x=USAJobsSource.map_result(item)
    assert x['source']=='usajobs'
    assert x['company']=='Example Agency'
    assert x['location']=='Seattle, Washington'
    assert x['salary_max']==145000
    assert x['application_url'].endswith('/apply/42')


def test_company_career_extracts_jobposting_jsonld():
    html='''<html><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting","title":"Software Engineer, AI",
      "description":"<p>Build reliable AI products.</p>","datePosted":"2026-09-12",
      "validThrough":"2026-10-01","url":"https://careers.example.com/jobs/1",
      "hiringOrganization":{"name":"Example Robotics"},
      "jobLocation":{"address":{"addressLocality":"Bellevue","addressRegion":"WA","addressCountry":"US"}},
      "baseSalary":{"value":{"minValue":130000,"maxValue":170000}}
    }</script></html>'''
    rows=CompanyCareerSource.extract_jobpostings(html,'https://careers.example.com','Example')
    assert len(rows)==1
    assert rows[0]['company']=='Example Robotics'
    assert rows[0]['title']=='Software Engineer, AI'
    assert 'Bellevue' in rows[0]['location']
    assert rows[0]['salary_min']==130000


def test_alert_inbox_identifies_linkedin_and_indeed_links():
    assert infer_provider('jobalerts-noreply@linkedin.com','New jobs for AI Engineer')=='linkedin'
    assert infer_provider('alert@indeed.com','Software Engineer jobs')=='indeed'
    html='''<a href="https://www.linkedin.com/jobs/view/123">AI Engineer</a>
            <a href="https://www.indeed.com/viewjob?jk=abc">Data Engineer</a>'''
    urls=extract_alert_urls('',html)
    assert any('linkedin.com/jobs/view/123' in x for x in urls)
    assert any('indeed.com/viewjob' in x for x in urls)
    candidates=extract_alert_candidates('',html)
    assert any(x['title']=='AI Engineer' for x in candidates)


def test_starter_discovery_matrix_contains_requested_channels():
    specs=starter_source_specs()
    names={x[1] for x in specs}; types={x[0] for x in specs}
    for name in {'OpenAI','Palantir','SpaceX','Microsoft','Amazon','Boeing','Meta','Salesforce','LinkedIn Job Alert Inbox','Indeed Job Alert Inbox','Adzuna Broad Market','USAJOBS'}:
        assert name in names
    for typ in {'ashby','lever','company_career','linkedin_alerts','indeed_alerts','adzuna','usajobs'}:
        assert typ in types

from careerops.db.models import CandidateProfile
from careerops.services.search_policy import evaluate_job_role

def test_role_filter_keeps_technical_and_rejects_unrelated_titles():
    p=CandidateProfile(full_name='X',role_families=['AI Engineer','Software Engineer','Data Engineer'])
    assert evaluate_job_role(p,'Machine Learning Engineer')['status']=='PASS'
    assert evaluate_job_role(p,'Accounts Payable Manager')['status']=='FAIL'

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from careerops.db.base import Base
from careerops.services.ingest import upsert_job

def test_cross_source_dedupe_prefers_official_source():
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
    with Session(engine) as db:
        a,_=upsert_job(db,{'source':'adzuna','source_job_id':'a1','company':'Acme','title':'AI Engineer','location':'Seattle, WA','description':'AI role','application_url':'https://adzuna.example/1'})
        b,created=upsert_job(db,{'source':'company_career','source_job_id':'official-1','company':'Acme','title':'AI Engineer','location':'Seattle, WA','description':'Official AI role','application_url':'https://acme.example/jobs/1'})
        assert created is False and a.id==b.id
        assert b.source=='company_career'
        assert b.application_url=='https://acme.example/jobs/1'

from careerops.services.alert_inbox import parse_rfc822

def test_rfc822_alert_parser_extracts_subject_and_body():
    raw='''From: jobs-noreply@linkedin.com\nSubject: New jobs for AI Engineer\nMessage-ID: <abc@example.com>\nContent-Type: text/html; charset=utf-8\n\n<a href="https://www.linkedin.com/jobs/view/999">AI Engineer</a>'''
    x=parse_rfc822(raw)
    assert x['subject']=='New jobs for AI Engineer'
    assert 'linkedin.com/jobs/view/999' in (x['html'] or '')
    assert x['message_id']=='<abc@example.com>'
