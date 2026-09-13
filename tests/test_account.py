from careerops.agents.browser import detect_portal

def test_portal_detection():
    assert detect_portal('https://company.wd5.myworkdayjobs.com/x')=='workday'
    assert detect_portal('https://job-boards.greenhouse.io/x')=='greenhouse'
    assert detect_portal('https://careers.google.com/jobs/1')=='google'
