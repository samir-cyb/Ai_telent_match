import json
from core.utils.llm_client import llm_generate as _llm_generate


def get_effectiveness_report(application_id):
    """
    Entry point called from AIEffectivenessView.
    Fetches the application, student and job, then runs the AI analysis.
    Returns a dict ready for JsonResponse.
    """
    from core.models import Application
    from django.shortcuts import get_object_or_404

    try:
        application = Application.objects.select_related(
            'student', 'job', 'job__company'
        ).get(id=application_id)
    except Application.DoesNotExist:
        return {
            'probability': 0,
            'explanation': 'Application not found.',
            'error': True
        }

    student = application.student
    job     = application.job

    result = analyze_effectiveness(student, job, application)
    result['student_name']  = student.name
    result['job_title']     = job.title
    result['company_name']  = job.company.name
    result['match_score']   = float(application.match_score or 0)
    result['trust_score']   = float(student.trust_score or 0)
    return result


def analyze_effectiveness(student, job, application):
    """
    Returns a dict: { "probability": int, "explanation": str }
    Uses Gemini to estimate how likely this student is to succeed in the role.
    """
    # ---- Gather student data ----
    skills = [
        {"name": ss.skill.name, "level": ss.proficiency_level}
        for ss in student.student_skills.select_related('skill').all()
    ]
    projects = [
        {
            "title": p.title,
            "description": p.description,
            "tech_stack": [s.name for s in p.tech_stack.all()]
        }
        for p in student.projects.all()
    ]
    experiences = [
        {
            "company": e.company_name,
            "role": e.role,
            "start": e.start_date.isoformat() if e.start_date else None,
            "end": e.end_date.isoformat() if e.end_date else None,
            "current": e.is_current,
        }
        for e in student.experiences.all()
    ]

    github_data = {
        "username": student.github_username,
        "verified": student.github_verified,
        "score": float(student.github_score or 0),
    }
    linkedin_data = student.linkedin_parsed_data or {}
    trust_score   = float(student.trust_score or 0)
    match_score   = float(application.match_score or 0)

    job_data = {
        "title": job.title,
        "description": job.description,
        "required_skills": [s.name for s in job.required_skills.all()],
        "job_type": job.job_type,
        "department_category": job.department_category,
        "min_cgpa": float(job.min_cgpa) if job.min_cgpa else None,
    }

    prompt = f"""
You are an expert talent evaluator. Given the candidate profile and job description below,
estimate the probability (0–100) that this candidate will be SUCCESSFUL in the role.

Return ONLY a JSON object with:
- "probability": integer (0-100)
- "explanation": string (2-3 sentences on key strengths/gaps and why this score)

Candidate:
- Name: {student.name}
- Department: {student.department}
- CGPA: {student.cgpa}
- Skills: {skills}
- Projects: {projects}
- Work Experience: {experiences}
- GitHub: {github_data}
- LinkedIn summary: {linkedin_data}
- Trust Score (0-100): {trust_score}
- AI Match Score for this job (0-100): {match_score}

Job:
- Title: {job_data["title"]}
- Description: {job_data["description"]}
- Required Skills: {job_data["required_skills"]}
- Job Type: {job_data["job_type"]}
- Department: {job_data["department_category"]}
- Min CGPA: {job_data["min_cgpa"]}

Evaluate: hard skill alignment, work experience, CGPA, external validation (GitHub/LinkedIn/trust),
and overall role fit. Be realistic about both strengths and gaps.

Output ONLY the JSON object. No extra text.
"""
    try:
        raw = _llm_generate(prompt, preferred_model='gemini-2.0-flash-lite').strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        data = json.loads(raw.strip())
        return {
            "probability": int(data.get("probability", 50)),
            "explanation": data.get("explanation", "No explanation provided.")
        }
    except Exception as e:
        return {
            "probability": int(match_score),
            "explanation": f"AI analysis unavailable. Using match score ({match_score:.0f}%) as proxy. ({e})"
        }
