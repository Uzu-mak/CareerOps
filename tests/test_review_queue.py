"""After a browser run, the review list is what the form still needs, not leftovers."""
from types import SimpleNamespace

from careerops.services.application_tracking import next_review_queue


def run(manual, filled=()):
    return SimpleNamespace(manual_fields=list(manual), filled_fields=list(filled))


SEEN = {'Major': {'field_type': 'text'}, 'Why us?': {'field_type': 'textarea'}, 'Page 2 question': {'field_type': 'select'}}


def test_a_completed_run_is_the_authority():
    previous = ['What is your desired salary?', 'Major', 'Why us?']        # a generic guess + earlier form questions
    assert next_review_queue(previous, SEEN, run(['Why us?', 'final submission approval'], filled=['Major'])) == ['Why us?', 'final submission approval']
    assert next_review_queue(previous, SEEN, run([], filled=['Major', 'Why us?'])) == []


def test_a_run_that_stopped_early_keeps_form_questions_it_never_reached():
    previous = ['What is your desired salary?', 'Major', 'Page 2 question']
    got = next_review_queue(previous, SEEN, run(['CAPTCHA'], filled=['Major']))
    assert got == ['CAPTCHA', 'Page 2 question']      # Major was filled; the generic guess was never on the form
