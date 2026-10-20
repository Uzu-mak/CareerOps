"""Saved sign-in sessions: which site a session belongs to and what counts as a session."""
import pytest

from careerops.services.portal_sessions import site_key, validate_state


def test_site_keys():
    assert site_key('https://www.metacareers.com/login?next=/jobs') == 'metacareers.com'
    assert site_key('https://amazon.jobs/en/jobs/1') == 'amazon.jobs'
    assert site_key('https://acme.wd5.myworkdayjobs.com/en-US/External/job/1') == 'acme.wd5.myworkdayjobs.com'   # per tenant
    assert site_key('https://careers.example.co.uk/apply') == 'example.co.uk'
    assert site_key('not a url') is None and site_key(None) is None


def test_session_must_contain_cookies():
    ok = validate_state({'cookies': [{'name': 'sid', 'value': '1'}], 'origins': [], 'extra': 'dropped'})
    assert ok == {'cookies': [{'name': 'sid', 'value': '1'}], 'origins': []}
    for bad in [None, [], {'origins': []}, {'cookies': [], 'origins': []}]:
        with pytest.raises(ValueError):
            validate_state(bad)
