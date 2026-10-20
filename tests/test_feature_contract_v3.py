from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_ui_exposes_every_section_and_all_source_types():
    from careerops.core.ui_options import SOURCE_TYPES
    base=(ROOT/'careerops/templates/base.html').read_text()
    sources=(ROOT/'careerops/templates/sources.html').read_text()
    for page in ['/jobs','/applications','/profile','/journal','/sources','/notifications']:
        assert f"nav_item('{page}'" in base
    for typ in ['greenhouse','lever','ashby','company_career','adzuna','usajobs','linkedin_alerts','indeed_alerts']:
        assert typ in SOURCE_TYPES
    assert 'ui.source_types.items()' in sources   # the add-source dropdown is generated from the shared list


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
    assert 'id="links"' in profile and 'data-form="add-link"' in profile
    assert 'Found in your resume' in profile                  # resume-derived skill suggestions
    assert 'account_plan' in job and 'Sign-in' in job          # portal account plan
    assert 'id="evidence"' in job and 'Career memory' in job   # ranked evidence for the role
    assert 'tradeoff' in journal.lower()
