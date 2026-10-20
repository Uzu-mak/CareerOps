"""Small-company discovery: HN "Who is hiring?", Remotive, and automatic ATS board discovery."""
from careerops.services.board_discovery import ats_board_from_url, boards_in_item
from careerops.sources.hn_hiring import parse_post
from careerops.sources.remotive import map_job


def hit(text, oid='49940381'):
    return {'objectID': oid, 'comment_text': text, 'created_at': '2026-10-03T00:54:01Z', 'parent_id': 49922569}


def test_hn_post_with_ats_link():
    job = parse_post(hit('Acme Robotics (YC W24) | Founding Backend Engineer, ML Engineer | Seattle, WA | Hybrid | $150k-$200k'
                         '<p>We build warehouse robots in Python and Rust.<p>Apply: <a href="https:&#x2F;&#x2F;jobs.ashbyhq.com&#x2F;acme-robotics&#x2F;123">'
                         'https:&#x2F;&#x2F;jobs.ashbyhq.com&#x2F;acme-robotics&#x2F;123</a>'))
    assert job['company'] == 'Acme Robotics (YC W24)'
    assert job['title'] == 'Founding Backend Engineer, ML Engineer'
    assert job['location'] == 'Seattle, WA' and job['workplace_type'] == 'hybrid'
    assert job['application_url'] == 'https://jobs.ashbyhq.com/acme-robotics/123'      # the ATS link wins
    assert job['canonical_url'] == 'https://news.ycombinator.com/item?id=49940381'
    assert 'warehouse robots' in job['description']
    assert boards_in_item(job) == [('ashby', 'acme-robotics')]


def test_hn_post_without_links_points_at_the_thread():
    job = parse_post(hit('Prophet Town LLC | Various Software Engineering Roles | US – Remote and Hybrid | Full-time'))
    assert job['title'] == 'Various Software Engineering Roles'
    assert job['workplace_type'] == 'remote' and 'Remote' in job['location']
    assert job['application_url'].startswith('https://news.ycombinator.com/item?id=')


def test_hn_replies_and_chatter_are_not_jobs():
    assert parse_post(hit('I briefly used Flutter and decided never again.')) is None
    assert parse_post(hit('')) is None


def test_ats_board_urls():
    assert ats_board_from_url('https://boards.greenhouse.io/stripe/jobs/123') == ('greenhouse', 'stripe')
    assert ats_board_from_url('https://job-boards.greenhouse.io/Anthropic/jobs/9') == ('greenhouse', 'anthropic')
    assert ats_board_from_url('https://boards.greenhouse.io/embed/job_app?for=figma&token=1') == ('greenhouse', 'figma')
    assert ats_board_from_url('https://jobs.lever.co/palantir/abc-123/apply') == ('lever', 'palantir')
    assert ats_board_from_url('https://jobs.eu.lever.co/acme/1') == ('lever', 'acme')
    assert ats_board_from_url('https://jobs.ashbyhq.com/openai') == ('ashby', 'openai')
    for not_a_board in ['https://boards.greenhouse.io/embed/job_app', 'https://example.com/jobs/1', 'https://jobs.lever.co/', None, 'not a url']:
        assert ats_board_from_url(not_a_board) is None


def test_remotive_mapping_keeps_attribution_and_links():
    job = map_job({'id': 7, 'url': 'https://remotive.com/remote-jobs/software-dev/x-7', 'title': 'Python Engineer', 'company_name': 'Tiny Co',
                   'job_type': 'full_time', 'publication_date': '2026-10-19T10:00:00', 'candidate_required_location': 'USA', 'salary': '$120k',
                   'description': '<p>Apply at <a href="https://jobs.lever.co/tinyco/1">our board</a></p>'})
    assert job['canonical_url'].startswith('https://remotive.com/') and job['raw_payload']['via'] == 'Remotive'
    assert job['workplace_type'] == 'remote' and job['location'] == 'USA' and 'Salary: $120k' in job['description']
    assert boards_in_item(job) == [('lever', 'tinyco')]
