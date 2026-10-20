"""Shared UI option lists and the view helpers the pages rely on."""
from datetime import datetime, timezone
from types import SimpleNamespace

from careerops.core.ui_options import (
    APPLICATION_STATUS_VALUES, SCAN_INTERVALS, SOURCE_TYPES, as_template_globals, detect_skills, review_input, suggest_roles,
)
from careerops.web.view_helpers import iso, money, salary_range, setup_checklist, short_dt


def test_skill_detection_uses_whole_words_and_aliases():
    text = 'Built FastAPI services on AWS with Postgres and k8s; good specs, excellent docs, Google Cloud; golang; C++ and C#.'
    found = detect_skills(text)
    for skill in ['FastAPI', 'AWS', 'PostgreSQL', 'Kubernetes', 'Go', 'C++', 'C#']:
        assert skill in found
    for false_positive in ['ECS', 'Excel']:   # "specs", "excellent"
        assert false_positive not in found


def test_review_questions_get_the_right_control():
    assert review_input('Are you legally authorized to work in the United States?') == {'kind': 'select', 'category': 'work_auth', 'options': ['Yes', 'No']}
    assert review_input('Have you ever been convicted of a felony?')['options'] == ['Yes', 'No']
    assert review_input('Gender')['kind'] == 'select'
    assert review_input('What are your salary expectations?')['kind'] == 'number'
    assert review_input('Why do you want to work at Initech? Please tell us in a few sentences.')['kind'] == 'textarea'
    assert review_input('Current company')['kind'] == 'text'


def test_option_lists_are_consistent():
    g = as_template_globals()
    assert {'submitted', 'interview', 'review'} <= APPLICATION_STATUS_VALUES
    assert set(g['status_label']) == APPLICATION_STATUS_VALUES
    assert 15 in {m for m, _ in SCAN_INTERVALS}
    assert all({'label', 'field', 'placeholder', 'key'} <= set(spec) for spec in SOURCE_TYPES.values())
    assert g['skills'] == sorted(g['skills'], key=str.lower) and len(set(g['skills'])) == len(g['skills'])
    assert suggest_roles('Worked as a Forward Deployed Engineer and Data Engineer') == ['Forward Deployed Engineer', 'Data Engineer']


def test_setup_checklist_tracks_what_is_missing():
    p = SimpleNamespace(baseline_resume_path='/r.pdf', legal_answers_verified_at=None, skills=['a', 'b'], role_families=['AI Engineer'],
                        linkedin_url='https://www.linkedin.com/in/your-name-123abc/', github_url='https://github.com/x')
    done = {i['key']: i['done'] for i in setup_checklist(p, 0, False)}
    assert done == {'resume': True, 'legal': False, 'skills': False, 'roles': True, 'links': False, 'alerts': False}
    assert setup_checklist(None) == []


def test_formatting_helpers():
    dt = datetime(2026, 10, 20, 17, 5, tzinfo=timezone.utc)
    assert iso(dt) == '2026-10-20T17:05:00+00:00'
    assert iso(datetime(2026, 10, 20, 17, 5)) == '2026-10-20T17:05:00+00:00'   # naive treated as UTC
    assert short_dt(dt) == 'Oct 20, 17:05 UTC' and short_dt(None) == '—'
    assert money(165000) == '$165k' and salary_range(170000, 240000) == '$170k – $240k' and salary_range(None, None) == 'Not listed'


def test_status_messages_are_explained_not_asked():
    from careerops.core.ui_options import blocker_info, is_blocker
    for reason in ['application form not detected', 'CAPTCHA', 'submission confirmation not detected', 'final submission approval',
                   'portal account password / email verification', 'form error: Email is invalid', 'truth guard - resume: 2 unverified claim(s) withheld']:
        info = blocker_info(reason)
        assert info and info['title'] and info['action'], reason
    assert blocker_info('form error: Email is invalid')['detail'] == 'Email is invalid'
    for question in ['Why do you want to work here?', 'Gender', 'Voluntary self-identification of disability']:
        assert not is_blocker(question)
