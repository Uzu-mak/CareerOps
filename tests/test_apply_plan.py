"""Answer planning for application forms: what gets filled, chosen, skipped or sent to review."""
from datetime import datetime, timezone
from types import SimpleNamespace

from careerops.agents.apply_plan import (
    Answer, bankable, build_facts, choose_option, classify, plan_application, same_question,
)


def profile(**overrides):
    values = dict(
        full_name='Ada King Lovelace', preferred_name='Ada', email='ada@example.com', phone='206-555-0100',
        home_location='Seattle, WA', linkedin_url='https://linkedin.com/in/ada', github_url='https://github.com/ada',
        legal_answers_verified_at=datetime.now(timezone.utc), authorized_to_work_us=True,
        requires_current_sponsorship=False, requires_future_sponsorship=False, eeo_preference=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def field(label, type='text', required=False, value='', options=None, key=None):
    opts = [{'id': f'o{i}', 'text': t, 'value': t} for i, t in enumerate(options or [])]
    return {'key': key or label, 'id': key or label, 'type': type, 'label': label, 'required': required,
            'value': value, 'options': opts}


def ops(plan):
    return {a.label: (a.op, a.value) for a in plan.actions}


def test_profile_fields_and_name_split():
    facts = build_facts(profile())
    plan = plan_application([field('First Name'), field('Last Name'), field('Full name'), field('Email'),
                             field('LinkedIn Profile'), field('Location (City)')], facts)
    got = ops(plan)
    assert got['First Name'] == ('fill', 'Ada')
    assert got['Last Name'] == ('fill', 'Lovelace')
    assert got['Full name'] == ('fill', 'Ada King Lovelace')
    assert got['Email'] == ('fill', 'ada@example.com')
    assert got['LinkedIn Profile'][1] == 'https://linkedin.com/in/ada'
    assert got['Location (City)'] == ('fill', 'Seattle, WA')


def test_verified_legal_answers_map_to_yes_no_options():
    facts = build_facts(profile(requires_future_sponsorship=True))
    plan = plan_application([
        field('Are you legally authorized to work in the United States?', 'radio', True, options=['Yes', 'No']),
        field('Do you currently require sponsorship?', 'select', True, options=['Select...', 'Yes', 'No']),
        field('Will you now or in the future require visa sponsorship?', 'select', True, options=['Select...', 'Yes', 'No']),
    ], facts)
    got = ops(plan)
    assert got['Are you legally authorized to work in the United States?'] == ('check', 'Yes')
    assert got['Do you currently require sponsorship?'] == ('select', 'No')
    assert got['Will you now or in the future require visa sponsorship?'] == ('select', 'Yes')
    assert plan.unresolved == []


def test_unverified_legal_answers_go_to_review():
    facts = build_facts(profile(legal_answers_verified_at=None))
    plan = plan_application([field('Are you legally authorized to work in the US?', 'radio', True, options=['Yes', 'No'])], facts)
    assert plan.actions == []
    assert plan.unresolved[0]['label'] == 'Are you legally authorized to work in the US?'
    assert 'not verified' in plan.unresolved[0]['reason']


def test_eeo_decline_preference_picks_decline_option():
    facts = build_facts(profile(eeo_preference='decline'))
    plan = plan_application([
        field('Gender', 'select', options=['Please select', 'Male', 'Female', 'Decline To Self Identify']),
        field('Veteran Status', 'select', options=['Select', 'I am a veteran', "I don't wish to answer"]),
        field('Disability Status', 'radio', options=['Yes, I have a disability', 'No', 'I do not want to answer']),
    ], facts)
    got = ops(plan)
    assert got['Gender'] == ('select', 'Decline To Self Identify')
    assert got['Veteran Status'] == ('select', "I don't wish to answer")
    assert got['Disability Status'] == ('check', 'I do not want to answer')


def test_eeo_without_preference_is_skipped_when_optional_and_reviewed_when_required():
    facts = build_facts(profile())
    plan = plan_application([field('Gender', 'select', options=['Male', 'Female', 'Decline']),
                             field('Race', 'select', True, options=['A', 'B', 'Decline'])], facts)
    assert plan.actions == []
    assert plan.skipped == ['Gender']
    assert [u['label'] for u in plan.unresolved] == ['Race']


def test_word_boundaries_avoid_false_sensitive_matches():
    assert classify('Preferred office: Brighton, East Sussex') == 'question'
    assert classify('Sex') == 'eeo'
    assert classify('Have you ever been convicted of a felony?') == 'criminal'
    assert classify('Are you at least 18 years of age?') == 'question'


def test_approved_answer_beats_everything_and_matches_reworded_question():
    facts = build_facts(profile(), approved_answers={'What is your desired salary?': '165000'})
    plan = plan_application([field('Desired salary', required=True)], facts)
    assert ops(plan)['Desired salary'] == ('fill', '165000')


def test_answer_bank_reuses_only_non_sensitive_answers():
    bank = {'How did you hear about us?': 'LinkedIn', 'Have you ever been convicted of a crime?': 'No',
            'What are your salary expectations?': '200000'}
    facts = build_facts(profile(), answer_bank=bank)
    plan = plan_application([
        field('How did you hear about this job?', 'select', True, options=['Select...', 'LinkedIn', 'Referral']),
        field('Have you ever been convicted of a crime?', 'radio', True, options=['Yes', 'No']),
        field('What are your salary expectations?', required=True),
    ], facts)
    assert ops(plan) == {'How did you hear about this job?': ('select', 'LinkedIn')}
    assert {u['label'] for u in plan.unresolved} == {'Have you ever been convicted of a crime?', 'What are your salary expectations?'}
    assert bankable('How did you hear about us?') and not bankable('Gender') and not bankable('Do you require sponsorship?')
    assert not bankable('Why do you want to work at Initech?')   # names the employer


def test_prefilled_values_are_kept_except_profile_facts():
    facts = build_facts(profile(), answer_bank={'Current company': 'Initech'})
    plan = plan_application([field('Current company', value='Globex'), field('Full name', value='PARSED NAME'),
                             field('Email', value='ada@example.com')], facts)
    assert ops(plan) == {'Full name': ('fill', 'Ada King Lovelace')}


def test_files_resume_first_input_and_cover_letter():
    facts = build_facts(profile(), resume_path='/tmp/r.pdf', cover_letter_path='/tmp/c.pdf')
    plan = plan_application([field('Resume/CV', 'file', True), field('Cover Letter', 'file'), field('', 'file', key='x')], facts)
    assert [(a.label, a.value) for a in plan.actions] == [('Resume/CV', '/tmp/r.pdf'), ('Cover Letter', '/tmp/c.pdf')]
    plan = plan_application([field('Portfolio sample', 'file', True)], facts)
    assert plan.unresolved[0]['reason'] == 'required file upload'


def test_required_open_question_without_answer_is_unresolved_with_exact_text():
    plan = plan_application([field('Why do you want to work here?', 'textarea', True)], build_facts(profile()))
    assert plan.unresolved == [{'label': 'Why do you want to work here?', 'category': 'motivation',
                                'reason': 'required question with no saved answer'}]


def test_choose_option_variants():
    yes = Answer('Yes', 'verified', 'yesno')
    assert choose_option(['Select...', 'Yes, I am authorized', 'No'], yes) == 1
    assert choose_option(['No', 'Yes'], Answer('No', 'verified', 'yesno')) == 0
    assert choose_option(['I agree to the privacy notice'], yes) == 0
    assert choose_option(['Male', 'Female'], Answer('decline', 'eeo-preference', 'decline')) is None
    assert choose_option(['Seattle, Washington, United States', 'Auburn'], Answer('Seattle, WA', 'profile')) == 0
    assert choose_option(['Company website', 'LinkedIn'], Answer('linkedin', 'answer-bank')) == 1
    assert choose_option(['Apples', 'Oranges'], Answer('LinkedIn', 'answer-bank')) is None


def test_same_question():
    assert same_question('How did you hear about us?', 'How did you hear about this job?')
    assert same_question('Desired salary', 'What is your desired salary?')
    assert not same_question('Gender', 'Gender identity and pronouns preference for the team')
    assert not same_question('Are you authorized to work?', 'Do you require sponsorship?')


def test_check_all_that_apply_answers_check_each_option():
    facts = build_facts(profile(), approved_answers={'Language Skill(s) (Check all that apply)': 'English | Twi'})
    plan = plan_application([field('Language Skill(s) (Check all that apply)', 'checkbox_group', True, options=['English', 'French', 'Twi'])], facts)
    assert [a.value for a in plan.actions] == ['English', 'Twi']


def test_time_sensitive_answers_are_never_reused():
    assert not bankable('Do you have any upcoming offer deadlines?')
    assert not bankable('What is your earliest start date?')
    assert not bankable("If Palantir didn't exist, what company would you work at?")   # names the employer
    assert bankable("What is the hardest technical challenge you've faced?")


def test_education_questions_are_filled_from_the_profile():
    facts = build_facts(profile(education_school='University of Washington', education_degree="Bachelor's", education_field='Computer Science',
                                education_graduation_year=2026, education_gpa='3.6', high_school_name='Accra Academy', high_school_graduation_year=2019))
    plan = plan_application([
        field('Which university are you currently attending or did you last attend? Please select "Other (School Not Listed)" if your school is not listed.',
              'select', True, options=['Select...', 'Stanford University', 'University of Washington', 'Other (School Not Listed)']),
        field('Please include your intended graduation year for the degree you are pursuing.', 'select', True, options=['2025', '2026', '2027']),
        field('High School Name', required=True), field('Year of High School Graduation', required=True),
        field('Highest level of education', 'select', options=["Bachelor's Degree", "Master's Degree"]),
        field('Major', required=True), field('GPA'),
    ], facts)
    got = ops(plan)
    assert got['Which university are you currently attending or did you last attend? Please select "Other (School Not Listed)" if your school is not listed.'] == ('select', 'University of Washington')
    assert got['Please include your intended graduation year for the degree you are pursuing.'] == ('select', '2026')
    assert got['High School Name'] == ('fill', 'Accra Academy') and got['Year of High School Graduation'] == ('fill', '2019')
    assert got['Highest level of education'] == ('select', "Bachelor's Degree")
    assert got['Major'] == ('fill', 'Computer Science') and got['GPA'] == ('fill', '3.6')
    assert plan.unresolved == []


def test_unlisted_school_picks_other():
    facts = build_facts(profile(education_school='Bellevue College'))
    plan = plan_application([field('Which university did you attend?', 'select', True, options=['Stanford University', 'Other (School Not Listed)'])], facts)
    assert ops(plan) == {'Which university did you attend?': ('select', 'Other (School Not Listed)')}


def test_work_authorization_answered_in_sentences():
    opts = ['Select...', 'I am authorized to work in the United States for any employer',
            'I am authorized to work in the United States but will require sponsorship now or in the future',
            'I am not authorized to work in the United States']
    q = 'Are you legally authorized to work in the United States?'
    got = ops(plan_application([field(q, 'select', True, options=opts)], build_facts(profile())))
    assert got[q] == ('select', opts[1])
    got = ops(plan_application([field(q, 'select', True, options=opts)], build_facts(profile(requires_future_sponsorship=True))))
    assert got[q] == ('select', opts[2])
    got = ops(plan_application([field(q, 'select', True, options=opts)], build_facts(profile(authorized_to_work_us=False))))
    assert got[q] == ('select', opts[3])
    two = ['I am authorized for any employer', 'I am authorized for my present employer only']
    plan = plan_application([field(q, 'select', True, options=two)], build_facts(profile(requires_future_sponsorship=None, requires_current_sponsorship=None)))
    assert plan.actions == [] and plan.unresolved   # ambiguous: you decide


def test_address_comes_from_the_profile_and_is_not_confused_with_email():
    facts = build_facts(profile(street_address='123 Main St, Seattle, WA 98101'))
    got = ops(plan_application([field('Address', 'textarea', True), field('Email address', required=True)], facts))
    assert got == {'Address': ('fill', '123 Main St, Seattle, WA 98101'), 'Email address': ('fill', 'ada@example.com')}
    plan = plan_application([field('Address', 'textarea', True)], build_facts(profile()))
    assert 'mailing address' in plan.unresolved[0]['reason']
