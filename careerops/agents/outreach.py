from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis


def draft_outreach(profile: CandidateProfile, job: JobPosting, analysis: JobAnalysis) -> str:
    strengths = ', '.join(analysis.matched_skills[:4]) or 'software, data, and applied AI systems'
    return (f"Hi — I just applied for the {job.title} role at {job.company}. My background includes {strengths}, "
            f"along with end-to-end experience building and deploying production-oriented systems. The role's focus looks closely aligned with the problems I've been working on, and I'd be glad to share more context on the projects most relevant to the team. Thanks for your time — {profile.preferred_name or profile.full_name.split()[0]}")
