"""Finishing in your own browser: CareerOps fills, you submit; and an ignored submit is reported honestly."""
from types import SimpleNamespace

from careerops.agents.apply_plan import build_facts
from careerops.core.ui_options import blocker_info


def test_host_script_facts_come_from_plain_json():
    # finish.py rebuilds the profile from the fill-kit JSON (datetimes arrive as strings)
    p = SimpleNamespace(full_name='Ada Lovelace', email='ada@example.com', legal_answers_verified_at='2026-10-20T10:00:00+00:00',
                        authorized_to_work_us=True, requires_current_sponsorship=False, requires_future_sponsorship=False,
                        street_address='1 Main St, Seattle, WA 98101')
    facts = build_facts(p, [], {'Why us?': 'Because'}, {})
    assert facts.legal_verified and facts.authorized is True and facts.address.startswith('1 Main')
    assert facts.approved == {'Why us?': 'Because'}


def test_refused_submission_is_a_blocker_that_says_you_have_not_applied():
    info = blocker_info('submission not accepted by the site')
    assert info and 'not applied' in info['why'] and 'Finish in your browser' in info['action']
