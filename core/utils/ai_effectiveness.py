import json
from google import genai
from django.conf import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

def analyze_effectiveness(student, job, application):
    """
    Returns a dict: { "probability": float, "explanation": str }
    """
    # ---- Gather student data ----
    skills = [{"name": ss.skill.name, "level": ss.proficiency_level}
              for ss in student.student_skills.select_related('skill')]
    projects = [{"title": p.title, "description": p.description,
                 "tech_stack": [s.name for s in p.tech_stack.all()]}
                for p in student.projects.all()]
    experiences = [{"company": e.company_name, "role": e.role,
                    "start": e.start_date.isoformat() if e.start_date else None,
                    "end": e.end_date.isoformat() if e.end_date else None,
                    "current": e.is_current}
                   for e in student.experiences.all()]

    github_data = {
        "username": student.github_username,
        "verified": student.github_verified,
        "score": student.github_score,
    }
    linkedin_data = student.linkedin_parsed_data or {}
    trust_score = float(student.trust_score or 0)
    match_score = float(application.match_score or 0)

    job_data = {
        "title": job.title,
        "description": job.description,
        "required_skills": [s.name for s in job.required_skills.all()],
        "job_type": job.job_type,
        "department_category": job.department_category,
        "min_cgpa": float(job.min_cgpa) if job.min_cgpa else None,
    }

    # ---- Build prompt ----
    prompt = f"""
You are an expert talent evaluator. Given the following candidate profile and job description, estimate the probability (0–100%) that this candidate will be **successful** in the role.

Return ONLY a JSON object with fields:
- "probability": integer (0-100)
- "explanation": string (2-3 sentences summarizing key strengths and weaknesses, and the main reason for the score)

Candidate Profile:
- Name: {student.name}
- Department: {student.department}
- CGPA: {student.cgpa}
- Skills: {skills}
- Projects: {projects}
- Work Experience: {experiences}
- GitHub: {github_data}
- LinkedIn: {linkedin_data}
- Trust Score (0-100): {trust_score}
- AI Match Score for this job (0-100): {match_score}

Job Details:
- Title: {job_data["title"]}
- Description: {job_data["description"]}
- Required Skills: {job_data["required_skills"]}
- Job Type: {job_data["job_type"]}
- Department Category: {job_data["department_category"]}
- Minimum CGPA: {job_data["min_cgpa"]}

Base your assessment on:
1. Hard skills alignment (required skills vs candidate's skills/projects).
2. Soft skills and experience (work history, roles, responsibilities).
3. Academic performance (CGPA relative to requirement).
4. External validation (GitHub activity, LinkedIn verification, trust score).
5. Overall fit for the role and company.

Be realistic and consider both strengths and gaps.

Output ONLY the JSON object. No extra text.
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",   # or "gemini-2.5-flash-lite"
            contents=prompt
        )
        raw = response.text.strip()
        # Remove markdown code fences if present
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        data = json.loads(raw)
        return {
            "probability": int(data.get("probability", 50)),
            "explanation": data.get("explanation", "No explanation provided.")
        }
    except Exception as e:
        # Fallback: use match score as a proxy
        return {
            "probability": int(match_score),
            "explanation": f"AI analysis unavailable. Using match score ({match_score}%) as proxy."
        }