from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_ui_exposes_notifications_journal_applications_and_new_source_types():
    base=(ROOT/'careerops/templates/base.html').read_text()
    dash=(ROOT/'careerops/templates/dashboard.html').read_text()
    assert "href='/notifications'" in base
    assert "href='/journal'" in base
    assert "href='/applications'" in base
    for typ in ['company_career','adzuna','usajobs','linkedin_alerts','indeed_alerts']:
        assert f"value='{typ}'" in dash


def test_compose_watchtower_runs_every_15_minutes_and_preserves_postgres():
    text=(ROOT/'docker-compose.yml').read_text()
    assert 'sleep 900' in text
    assert 'careerops_postgres:/var/lib/postgresql/data' in text
    assert '5433:5432' in text
    assert '8001:8000' in text


def test_profile_and_job_pages_expose_living_evidence_and_account_plan():
    profile=(ROOT/'careerops/templates/profile.html').read_text()
    job=(ROOT/'careerops/templates/job.html').read_text()
    journal=(ROOT/'careerops/templates/journal.html').read_text()
    assert 'LinkedIn URL' in profile and 'GitHub URL' in profile
    assert 'PUBLIC / APPLICATION LINKS' in profile
    assert 'LIVING CAREER EVIDENCE' in profile
    assert 'Portal account plan' in job
    assert 'CAREER MEMORY RETRIEVAL' in job
    assert 'tradeoff' in journal.lower()
