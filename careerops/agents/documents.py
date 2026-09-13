from __future__ import annotations
from html import escape
from sqlalchemy.orm import Session
from sqlalchemy import select
from weasyprint import HTML
from careerops.core.config import settings
from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis, GeneratedArtifact, Application, ProfileLink
from careerops.agents.evidence import rank_evidence
from careerops.agents.truth_guard import verify_generated_claims
from careerops.services.resume_baseline import extract_section_lines

BASE_CSS = '''
@page { size: Letter; margin: 0.5in; }
body { font-family: Arial, sans-serif; color:#172033; font-size:10pt; line-height:1.25; }
h1 { font-size:18pt; margin:0; } h2 { font-size:11pt; border-bottom:1px solid #9aa5b5; padding-bottom:2px; margin:9px 0 4px; }
h3 { font-size:10pt; margin:5px 0 2px; } p { margin:3px 0; } ul { margin:2px 0 6px 18px; padding:0; }
.meta { color:#4b5565; font-size:9pt; } .accent { color:#3157d5; } .letter p { margin:0 0 9px; }
'''


def _safe(s): return escape(s or '')


def _relevant_skills(profile: CandidateProfile, analysis: JobAnalysis) -> list[str]:
    wanted = [x.lower() for x in (analysis.matched_skills + analysis.partial_skills + analysis.gap_skills)]
    skills = list(profile.skills or [])
    skills.sort(key=lambda x: (x.lower() not in wanted, wanted.index(x.lower()) if x.lower() in wanted else 999, x.lower()))
    return skills


def build_resume(db: Session, profile: CandidateProfile, job: JobPosting, analysis: JobAnalysis, application: Application | None = None) -> GeneratedArtifact:
    """Generate a job-specific resume while treating the user's uploaded master resume as baseline.

    CareerOps changes emphasis, summary, skill ordering and evidence ordering. It does not
    invent employers, projects, dates or impact metrics. Claims must exist in structured
    verified evidence or in the user's uploaded master resume.
    """
    evidence = rank_evidence(db, profile, job, limit=5)
    key_skills = analysis.matched_skills[:10] + analysis.partial_skills[:4]
    summary = (
        f"Applied AI / Software Engineer targeting {job.title}, with experience across software, data and AI systems. "
        f"Most relevant strengths for {job.company}: {', '.join(key_skills[:8])}."
        if key_skills else
        f"Applied AI / Software Engineer targeting {job.title}, with experience across software, data and AI systems."
    )

    extra_links=db.scalars(select(ProfileLink).where(ProfileLink.profile_id==profile.id, ProfileLink.include_in_applications==True).order_by(ProfileLink.id).limit(2)).all()
    meta_bits=[profile.home_location, profile.email, profile.linkedin_url, profile.github_url] + [x.url for x in extra_links]
    parts = [
        f"<h1>{_safe(profile.full_name)}</h1>",
        f"<div class='meta'>{' | '.join(_safe(x) for x in meta_bits if x)}</div>",
        '<h2>SUMMARY</h2>', f'<p>{_safe(summary)}</p>',
        '<h2>EXPERIENCE & PROJECTS</h2>'
    ]
    body_text = summary
    emitted = set()
    for e in evidence:
        parts.append(f"<h3>{_safe(e.title)}{(' | ' + _safe(e.organization)) if e.organization else ''}{(' | ' + _safe(e.date_range)) if e.date_range else ''}</h3><ul>")
        bullets = list(e.bullets or [])
        wanted = [s.lower() for s in (job.required_skills or []) + (job.preferred_skills or []) + analysis.matched_skills]
        bullets.sort(key=lambda b: -sum(1 for k in wanted if k and k in b.lower()))
        for b in bullets[:3]:
            parts.append(f'<li>{_safe(b)}</li>')
            body_text += ' ' + b
            emitted.add(' '.join(b.lower().split()))
        parts.append('</ul>')

    # Preserve the user's education section from the uploaded master resume verbatim.
    education = extract_section_lines(profile, 'EDUCATION') if profile.baseline_resume_text else []
    if education:
        parts.append('<h2>EDUCATION</h2>')
        for line in education[:4]:
            parts.append(f'<p>{_safe(line)}</p>'); body_text += ' ' + line

    parts += ['<h2>TECHNICAL SKILLS</h2>', f"<p>{_safe(', '.join(_relevant_skills(profile, analysis)))}</p>"]
    html = f"<html><head><style>{BASE_CSS}</style></head><body>{''.join(parts)}</body></html>"
    passed, blocked = verify_generated_claims(body_text, evidence, profile.baseline_resume_text or '')
    if blocked:
        html += '<!-- truth-guard blocked claims: ' + _safe(' | '.join(blocked)) + ' -->'
    source_name = profile.baseline_resume_filename or 'structured candidate evidence'
    art = GeneratedArtifact(
        job_id=job.id, application_id=application.id if application else None,
        artifact_type='resume', title=f'{job.company} - {job.title} - Tailored Resume',
        content=html + f'<!-- baseline: {_safe(source_name)} -->', truth_guard_passed=passed, blocked_claims=blocked
    )
    db.add(art); db.flush()
    path = settings.generated_path / f'job_{job.id}_resume_{art.id}.pdf'
    HTML(string=html).write_pdf(path)
    art.file_path = str(path); db.commit(); db.refresh(art)
    return art


def build_cover_letter(db: Session, profile: CandidateProfile, job: JobPosting, analysis: JobAnalysis, application: Application | None = None) -> GeneratedArtifact:
    evidence = rank_evidence(db, profile, job, limit=3)
    strongest = evidence[0] if evidence else None
    second = evidence[1] if len(evidence) > 1 else None
    matched = ', '.join(analysis.matched_skills[:7]) or 'software engineering and problem solving'
    mission = job.company_mission or f'the problems {job.company} is solving'
    paragraphs = [
        f"I am excited to apply for the {job.title} role at {job.company}. What draws me to the opportunity is the chance to combine {matched} with work that directly supports {mission}.",
        (f"One experience that maps closely to this role is {strongest.title}{' at ' + strongest.organization if strongest and strongest.organization else ''}. {strongest.summary} {strongest.bullets[0] if strongest and strongest.bullets else ''}" if strongest else ''),
        (f"I would also bring perspective from {second.title}. {second.summary} {second.bullets[0] if second and second.bullets else ''}" if second else ''),
        f"I am especially interested in the role's focus on {('; '.join((job.responsibilities or [])[:3])).lower() if job.responsibilities else 'building useful, reliable systems and collaborating across teams'}. I enjoy ambiguous problems where the right answer requires understanding the workflow, making clear technical tradeoffs, and owning the result through deployment and iteration.",
        f"I would welcome the opportunity to bring that combination of software, data, applied AI, reliability thinking, and strong stakeholder communication to {job.company}. Thank you for considering my application."
    ]
    paragraphs = [p for p in paragraphs if p]
    body = ' '.join(paragraphs)
    passed, blocked = verify_generated_claims(body, evidence, profile.baseline_resume_text or '')
    if blocked:
        paragraphs = [p for p in paragraphs if all(b not in p for b in blocked)]
    extra_links=db.scalars(select(ProfileLink).where(ProfileLink.profile_id==profile.id, ProfileLink.include_in_applications==True).order_by(ProfileLink.id).limit(1)).all()
    meta_bits=[profile.home_location, profile.email, profile.linkedin_url] + [x.url for x in extra_links]
    html = f"<html><head><style>{BASE_CSS}</style></head><body class='letter'><h1>{_safe(profile.full_name)}</h1><div class='meta'>{' | '.join(_safe(x) for x in meta_bits if x)}</div><p style='margin-top:18px'>Dear {_safe(job.company)} Hiring Team,</p>{''.join('<p>'+_safe(p)+'</p>' for p in paragraphs)}<p>Sincerely,<br><strong>{_safe(profile.full_name)}</strong></p></body></html>"
    art = GeneratedArtifact(job_id=job.id, application_id=application.id if application else None, artifact_type='cover_letter', title=f'{job.company} - {job.title} - Cover Letter', content=html, truth_guard_passed=not blocked, blocked_claims=blocked)
    db.add(art); db.flush()
    path = settings.generated_path / f'job_{job.id}_cover_letter_{art.id}.pdf'
    HTML(string=html).write_pdf(path)
    art.file_path = str(path); db.commit(); db.refresh(art)
    return art
