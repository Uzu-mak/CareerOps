"""End-to-end browser agent runs against realistic ATS fixtures in real Chromium.

The fixtures under tests/fixtures/ats mimic the markup and behaviour that broke
the previous agent: Lever's posting page and resume parser, a Greenhouse board
embedded from another origin with React-Select dropdowns and a location
autocomplete, Ashby's client-rendered form with Yes/No buttons, the invisible
reCAPTCHA badge, a real CAPTCHA challenge, and an account wall.
"""
import functools
import http.server
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip('playwright.sync_api')

from careerops.agents import browser  # noqa: E402
from careerops.core.config import settings  # noqa: E402

FIXTURES = Path(__file__).parent / 'fixtures' / 'ats'
_SERVER = {}


def _base() -> str:
    """Serve the fixtures once per test session; 'localhost' is a second origin for iframes."""
    if 'port' not in _SERVER:
        handler = functools.partial(_QuietHandler, directory=str(FIXTURES))
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _SERVER['port'] = server.server_address[1]
    return f'http://127.0.0.1:{_SERVER["port"]}'


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _profile(**overrides):
    values = dict(
        id=1, full_name='Ada Lovelace', preferred_name=None, email='ada@example.com', phone='206-555-0100',
        home_location='Seattle, WA', linkedin_url='https://www.linkedin.com/in/ada', github_url='https://github.com/ada',
        legal_answers_verified_at=datetime.now(timezone.utc), authorized_to_work_us=True,
        requires_current_sponsorship=False, requires_future_sponsorship=False, eeo_preference='decline',
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _files(tmp_path):
    resume, cover = tmp_path / 'resume.pdf', tmp_path / 'cover.pdf'
    resume.write_bytes(b'%PDF-1.4 resume'); cover.write_bytes(b'%PDF-1.4 cover')
    return str(resume), str(cover)


def _run(monkeypatch, tmp_path, path, profile=None, **kwargs):
    monkeypatch.setattr(settings, 'generated_dir', str(tmp_path))
    resume, cover = _files(tmp_path)
    return browser.run_generic_browser(
        profile or _profile(), SimpleNamespace(company='Acme', title='AI Engineer'), SimpleNamespace(id=42),
        f'{_base()}/{path}', resume_path=resume, cover_letter_path=cover,
        submit=kwargs.pop('submit', True), **kwargs,
    )


def _query(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}


BANK = {'How did you hear about this job?': 'LinkedIn'}
LEVER_ANSWERS = {'Language Skill(s) (Check all that apply)': 'English | Twi',
                 "What is the hardest technical challenge you've faced? (Approx. 200 words)": 'Making a browser agent fill real ATS forms.'}
LINKS = [{'label': 'Portfolio', 'url': 'https://ada.dev', 'link_type': 'portfolio', 'include_in_applications': True}]


def test_lever_pauses_with_clean_labels_and_the_forms_own_options(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'lever/apply.html', answer_bank=BANK)

    assert not result.submitted
    assert set(result.manual_fields) == set(LEVER_ANSWERS)          # exactly the two questions it can't know
    langs = result.manual_details['Language Skill(s) (Check all that apply)']
    assert langs['type'] == 'checkbox_group' and langs['options'] == ['English', 'French', 'Twi']
    assert result.manual_details["What is the hardest technical challenge you've faced? (Approx. 200 words)"]['type'] == 'textarea'
    assert 'Current location' in result.filled_fields               # label without "No location found…" chatter
    assert not any('No location' in f or 'ATTACH' in f for f in result.filled_fields)


def test_lever_posting_through_confirmation(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'lever/posting.html', answer_bank=BANK, extra_links=LINKS,
                  approved_review_answers=LEVER_ANSWERS)

    assert result.submitted, result.manual_fields
    assert result.status == 'SUBMITTED'
    assert result.confirmation_term in {'application submitted', 'thank you for applying'}
    sent = _query(result.url)
    assert sent['name'] == 'Ada Lovelace'                 # overwrote the resume parser's guess
    assert sent['email'] == 'ada@example.com' and sent['phone'] == '206-555-0100'
    assert sent['cards[0][field0]'] == 'Yes'              # verified: authorized to work
    assert sent['cards[0][field1]'] == 'No'               # verified: no sponsorship needed
    assert sent['cards[0][field3]'] == 'LinkedIn'         # reused from the answer bank
    assert sent['cards[0][field2]'] == ''                 # optional, unknown: left alone ("Sussex" is not EEO)
    assert sent['eeo[gender]'] == 'Decline to self-identify'
    assert sent['urls[Portfolio]'] == 'https://ada.dev'
    assert sent['selectedLocation'] == 'Seattle, Washington, United States'   # picked from the autocomplete
    assert sent['languages'] == 'English,Twi'                                 # multi-select answer
    assert sent['resume'] == 'resume.pdf'
    assert Path(result.screenshot_path).name == 'application_42_confirmation.png'


def test_prepare_mode_fills_but_never_submits(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'lever/apply.html', answer_bank=BANK, submit=False, approved_review_answers=LEVER_ANSWERS)

    assert not result.submitted
    assert result.status == 'READY_FOR_SUBMISSION'
    assert result.manual_fields == []
    assert 'apply.html' in result.url


def test_greenhouse_embed_across_origins(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'greenhouse/company.html', answer_bank=BANK)

    assert result.submitted, result.manual_fields
    sent = _query(result.url)
    assert (sent['first_name'], sent['last_name'], sent['email']) == ('Ada', 'Lovelace', 'ada@example.com')
    assert sent['q_auth'] == 'Yes' and sent['q_sponsor'] == 'No'    # React-Select comboboxes
    assert sent['location_choice'] == 'Seattle, Washington, United States'
    assert sent['q_source'] == 'li'
    assert sent['resume'] == 'resume.pdf' and sent['cover_letter'] == 'cover.pdf'
    assert (sent['gender'], sent['hispanic'], sent['veteran'], sent['disability']) == ('3', 'd', '3', '3')


def test_without_eeo_preference_optional_eeo_stays_blank(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'greenhouse/board.html', profile=_profile(eeo_preference=None), answer_bank=BANK)

    assert result.submitted, result.manual_fields
    sent = _query(result.url)
    assert sent['gender'] == '' and sent['veteran'] == '' and 'disability' not in sent


def test_ashby_pauses_on_exact_question_then_finishes_after_review(monkeypatch, tmp_path):
    first = _run(monkeypatch, tmp_path, 'ashby/application.html')

    assert not first.submitted
    assert first.manual_fields == ['Why do you want to work at Initech?']   # optional "Pronouns" is not a blocker

    answers = {'Why do you want to work at Initech?': 'I want to build reliable AI tooling for operations teams.'}
    second = _run(monkeypatch, tmp_path, 'ashby/application.html', approved_review_answers=answers)

    assert second.submitted, second.manual_fields
    assert second.confirmation_term in {'application submitted', 'successfully submitted', 'application was successfully submitted'}
    sent = _query(second.url)
    assert sent['name'] == 'Ada Lovelace' and sent['sponsor'] == 'No' and sent['resume'] == 'resume.pdf'
    assert sent['why'].startswith('I want to build')


def test_unverified_legal_answers_are_never_guessed(monkeypatch, tmp_path):
    profile = _profile(legal_answers_verified_at=None)
    result = _run(monkeypatch, tmp_path, 'lever/apply.html', profile=profile, answer_bank=BANK)

    assert not result.submitted
    assert 'Are you legally authorized to work in the United States?' in result.manual_fields
    assert 'Will you now or in the future require sponsorship for employment visa status?' in result.manual_fields


def test_captcha_challenge_pauses_instead_of_submitting(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'captcha/apply.html')

    assert not result.submitted
    assert 'CAPTCHA' in result.manual_fields
    assert 'submission confirmation not detected' in result.manual_fields


def test_account_wall_is_left_to_the_candidate(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'login/index.html')

    assert not result.submitted
    assert result.manual_fields == ['portal account password / email verification']


def test_lever_and_ashby_links_open_the_application_form():
    lever = 'https://jobs.lever.co/acme/0f8c2b0e-4c55-4c41-9f0a-1d2e3f4a5b6c'
    ashby = 'https://jobs.ashbyhq.com/initech/0f8c2b0e-4c55-4c41-9f0a-1d2e3f4a5b6c?src=li'
    assert browser.application_entry_url(lever) == lever + '/apply'
    assert browser.application_entry_url(ashby) == 'https://jobs.ashbyhq.com/initech/0f8c2b0e-4c55-4c41-9f0a-1d2e3f4a5b6c/application?src=li'
    assert browser.application_entry_url(lever + '/apply') == lever + '/apply'
    assert browser.application_entry_url('https://boards.greenhouse.io/x/jobs/1') == 'https://boards.greenhouse.io/x/jobs/1'


def _education(**overrides):
    return _profile(education_school='University of Washington', education_degree="Bachelor's", education_field='Computer Science',
                    education_graduation_year=2026, education_graduation_month=6, education_gpa=None,
                    high_school_name='Accra Academy', high_school_graduation_year=2019, **overrides)


def test_sign_in_wall_without_a_session_pauses(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, 'portal/apply.html', profile=_education())
    assert not result.submitted
    assert result.manual_fields == ['portal account password / email verification']


def test_saved_session_gets_past_the_wall_and_education_is_filled(monkeypatch, tmp_path):
    import json
    state = tmp_path / 'session.json'
    state.write_text(json.dumps({'cookies': [{'name': 'portal_session', 'value': 'valid', 'domain': '127.0.0.1', 'path': '/',
                                              'expires': -1, 'httpOnly': False, 'secure': False, 'sameSite': 'Lax'}], 'origins': []}))
    result = _run(monkeypatch, tmp_path, 'portal/apply.html', profile=_education(), storage_state=str(state))

    assert result.submitted, result.manual_fields
    assert result.used_session
    sent = _query(result.url)
    assert sent['school'] == 'Other (School Not Listed)'      # UW isn't listed, so the form's "Other"
    assert sent['grad'] == '2026'


def test_essays_are_written_mid_run_when_auto_answer_is_on(monkeypatch, tmp_path):
    asked = []

    def drafter(question):
        asked.append(question)
        return 'I made a browser agent fill real application forms reliably, tested against replicas of each portal.'

    answers = {'Language Skill(s) (Check all that apply)': 'English'}           # the essay is NOT pre-answered
    result = _run(monkeypatch, tmp_path, 'lever/apply.html', answer_bank=BANK, approved_review_answers=answers, drafter=drafter)

    assert result.submitted, result.manual_fields
    assert asked == ["What is the hardest technical challenge you've faced? (Approx. 200 words)"]
    assert list(result.auto_answers) == asked
    assert _query(result.url)['cards[0][field5]'].startswith('I made a browser agent')


def test_drafter_that_declines_still_pauses(monkeypatch, tmp_path):
    answers = {'Language Skill(s) (Check all that apply)': 'English'}
    result = _run(monkeypatch, tmp_path, 'lever/apply.html', answer_bank=BANK, approved_review_answers=answers, drafter=lambda q: None)
    assert not result.submitted
    assert result.manual_fields == ["What is the hardest technical challenge you've faced? (Approx. 200 words)"]
