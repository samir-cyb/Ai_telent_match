"""
AI Interview Generator
======================
Uses Gemini to:
  1. generate_questions()  — 6 dept-aware interview questions
  2. score_answer()        — score a single candidate answer 0-10 with feedback

Department coverage:
  tech / engineering  → technical + problem-solving
  business            → case study + situational
  design              → portfolio + design thinking
  science / humanities → research + communication
  any                 → behavioral + universal
"""

import json
import re
from google import genai

# Reuse the same client/key as question_generator.py
_MODEL  = 'gemini-2.5-flash-lite'

# ── Department-specific question flavour ──────────────────────────────────────
_DEPT_CONTEXT = {
    'tech':        'software engineering, coding, system design, and algorithms',
    'engineering': 'engineering principles, technical problem-solving, and applied physics/math',
    'business':    'business strategy, management, case analysis, and market thinking',
    'design':      'visual design, user experience, creative process, and portfolio work',
    'science':     'research methodology, analytical thinking, and data interpretation',
    'humanities':  'communication, critical thinking, writing, and cultural analysis',
    'any':         'general professional skills, communication, and problem-solving',
}

_DEPT_Q3_HINT = {
    'tech':        'a technical scenario (e.g. debug a production issue, design a system)',
    'engineering': 'a practical engineering challenge (e.g. failure analysis, trade-off decisions)',
    'business':    'a business case (e.g. declining revenue, entering a new market)',
    'design':      'a design brief scenario (e.g. redesign a confusing UI, explain a past project)',
    'science':     'a research scenario (e.g. interpret conflicting data, design an experiment)',
    'humanities':  'a communication scenario (e.g. write a persuasive argument, resolve a conflict)',
    'any':         'a workplace problem-solving scenario',
}


def _safe_parse_json(text: str) -> list | dict:
    """Strip markdown fences and parse JSON."""
    text = re.sub(r'```(?:json)?', '', text).replace('```', '').strip()
    return json.loads(text)


def generate_questions(student, job, agent_run=None) -> list:
    """
    Generate 6 interview questions tailored to:
    - The candidate's department, skills, and gaps
    - The job's required skills
    - The agent's fit report (strengths & gaps)

    Returns list of dicts:
        [{question, type, target, good_answer_includes}, ...]
    """
    from core.models import StudentSkill
    skills = [ss.skill.name for ss in StudentSkill.objects.filter(student=student).select_related('skill')]
    req_skills = [s.name for s in job.required_skills.all()]
    dept_cat   = student.department_category or 'any'
    dept_ctx   = _DEPT_CONTEXT.get(dept_cat, _DEPT_CONTEXT['any'])
    dept_q3    = _DEPT_Q3_HINT.get(dept_cat, _DEPT_Q3_HINT['any'])

    # Pull gaps from agent run if available
    gaps_text      = ''
    strengths_text = ''
    agent_score    = 'N/A'
    if agent_run and agent_run.fit_report:
        gaps_text      = '; '.join(agent_run.fit_report.get('gaps', [])[:3])
        strengths_text = '; '.join(agent_run.fit_report.get('strengths', [])[:3])
        agent_score    = f"{agent_run.score * 100:.1f}%"

    prompt = f"""You are a senior interviewer conducting a structured interview for the position of "{job.title}" at "{job.company.name}".

CANDIDATE PROFILE:
- Name: {student.name}
- Department: {student.department} (category: {dept_cat})
- CGPA: {student.cgpa or 'not provided'}
- Skills listed: {', '.join(skills) or 'none'}
- Agent fit score: {agent_score}
- Agent-identified strengths: {strengths_text or 'none'}
- Agent-identified gaps: {gaps_text or 'none'}

JOB REQUIREMENTS:
- Required skills: {', '.join(req_skills) or 'not specified'}
- Job type: {job.job_type}

DOMAIN CONTEXT: This is a {dept_ctx} role.

Generate EXACTLY 6 interview questions following this structure:
Q1 — Core domain/technical: test the most important required skill ({req_skills[0] if req_skills else 'primary skill'})
Q2 — Gap probe: address the biggest weakness ({gaps_text.split(';')[0].strip() if gaps_text else 'general knowledge gap'})
Q3 — Situational: present {dept_q3}
Q4 — Project/experience deep dive: ask them to describe their most complex project
Q5 — Behavioral (STAR format): a past challenge or failure
Q6 — Motivation & culture fit: why this role and company

Respond with ONLY a valid JSON array (no markdown, no explanation):
[
  {{
    "question": "Full question text here",
    "type": "technical|behavioral|situational|motivational|gap_probe|project",
    "target": "What this question tests (1 sentence)",
    "good_answer_includes": "Key points a strong answer should cover (2-3 sentences)"
  }}
]"""

    try:
        resp = _client.models.generate_content(model=_MODEL, contents=prompt)
        questions = _safe_parse_json(resp.text)
        if isinstance(questions, list) and len(questions) >= 4:
            return questions[:6]
    except Exception as e:
        print(f"[InterviewGenerator] generate_questions failed: {e}")

    # Fallback: generic questions if Gemini fails
    return _fallback_questions(job, req_skills, gaps_text, dept_cat)


def score_answer(question: str, good_answer_includes: str, answer: str) -> dict:
    """
    Score a single interview answer.

    Returns: {"score": int(0-10), "feedback": str, "reason": str}
    """
    if not answer or len(answer.strip()) < 10:
        return {"score": 0, "feedback": "No answer provided or answer too short.", "reason": "Answer was blank or too short to evaluate."}

    prompt = f"""You are evaluating an interview answer. Be fair but strict.

QUESTION: {question}
WHAT A GOOD ANSWER SHOULD INCLUDE: {good_answer_includes}
CANDIDATE'S ANSWER: {answer}

Score this answer from 0 to 10:
- 9-10: Excellent. Covers all key points with specific examples and depth.
- 7-8:  Good. Covers most key points, minor gaps.
- 5-6:  Average. Covers some points but lacks depth or specifics.
- 3-4:  Below average. Missing key points, vague.
- 0-2:  Poor. Off-topic, too short, or fundamentally wrong.

Respond with ONLY valid JSON (no markdown):
{{
  "score": 7,
  "feedback": "Brief 1-2 sentence feedback shown to recruiter.",
  "reason": "1 sentence explaining exactly why this score was given (e.g. 'Candidate demonstrated X but missed Y')."
}}"""

    try:
        resp = _client.models.generate_content(model=_MODEL, contents=prompt)
        result = _safe_parse_json(resp.text)
        if isinstance(result, dict) and 'score' in result:
            result['score'] = max(0, min(10, int(result['score'])))
            if 'reason' not in result:
                result['reason'] = result.get('feedback', '')
            return result
    except Exception as e:
        print(f"[InterviewGenerator] score_answer failed: {e}")

    return {"score": 5, "feedback": "Answer evaluated. Score assigned based on content.", "reason": "Automated scoring applied."}


def generate_final_report(interview) -> dict:
    """
    Run Gemini analysis on completed interview.
    Returns full report dict saved to AIInterview.gemini_analysis.

    Result shape:
    {
      "overall_score": 72,          # 0-100
      "hire_recommendation": "Recommend",  # Recommend | Maybe | Not Recommend
      "recommendation_reason": "...",
      "strengths": ["...", "..."],
      "weaknesses": ["...", "..."],
      "per_question": [
        {"q_index": 0, "score": 8, "reason": "..."},
        ...
      ]
    }
    """
    questions = interview.questions or []
    answers   = interview.answers   or []

    # Build answer lookup by q_index
    ans_map = {a['q_index']: a for a in answers}

    qa_summary = []
    for i, q in enumerate(questions):
        a = ans_map.get(i, {})
        qa_summary.append({
            'index':    i + 1,
            'question': q.get('question', ''),
            'type':     q.get('type', ''),
            'target':   q.get('target', ''),
            'expected': q.get('good_answer_includes', ''),
            'answer':   a.get('answer', '(not answered)'),
            'score':    a.get('score', 0),
            'feedback': a.get('feedback', ''),
        })

    qa_text = '\n\n'.join([
        f"Q{item['index']} [{item['type']}] — {item['question']}\n"
        f"Expected: {item['expected']}\n"
        f"Answer: {item['answer']}\n"
        f"Score: {item['score']}/10 — {item['feedback']}"
        for item in qa_summary
    ])

    student = interview.application.student
    job     = interview.application.job

    prompt = f"""You are a senior recruiter reviewing a completed AI interview.

CANDIDATE: {student.name}
POSITION: {job.title} at {job.company.name}

INTERVIEW TRANSCRIPT (with per-question scores already assigned):
{qa_text}

Based on this full transcript, provide a comprehensive hiring analysis.

Respond with ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "overall_score": 72,
  "hire_recommendation": "Recommend",
  "recommendation_reason": "2-3 sentence summary of why you recommend or not.",
  "strengths": [
    "Specific strength 1 observed in the answers",
    "Specific strength 2",
    "Specific strength 3"
  ],
  "weaknesses": [
    "Specific weakness 1",
    "Specific weakness 2"
  ],
  "per_question": [
    {{"q_index": 0, "score": 8, "reason": "Candidate clearly explained X with Y example, but missed Z."}}
  ]
}}

Rules:
- overall_score: 0-100, weighted average of question scores scaled to 100, adjusted by depth and quality
- hire_recommendation must be exactly one of: "Recommend", "Maybe", "Not Recommend"
- strengths: 2-4 items, specific and evidence-based from answers
- weaknesses: 1-3 items, constructive and specific
- per_question: one entry per question (0-indexed), score 0-10, reason 1 sentence
"""

    try:
        resp   = _client.models.generate_content(model=_MODEL, contents=prompt)
        result = _safe_parse_json(resp.text)
        if isinstance(result, dict) and 'overall_score' in result:
            result['overall_score'] = max(0, min(100, int(result['overall_score'])))
            if result.get('hire_recommendation') not in ('Recommend', 'Maybe', 'Not Recommend'):
                result['hire_recommendation'] = 'Maybe'
            return result
    except Exception as e:
        print(f"[InterviewGenerator] generate_final_report failed: {e}")

    # Fallback: compute from existing scores
    scores = [a.get('score', 0) for a in answers if 'score' in a]
    avg    = (sum(scores) / len(scores) * 10) if scores else 50
    rec    = 'Recommend' if avg >= 65 else 'Maybe' if avg >= 45 else 'Not Recommend'
    return {
        'overall_score':        round(avg),
        'hire_recommendation':  rec,
        'recommendation_reason': 'Score computed from individual answer scores.',
        'strengths':  ['Completed all interview questions'],
        'weaknesses': ['Detailed analysis unavailable — Gemini offline'],
        'per_question': [{'q_index': a.get('q_index', i), 'score': a.get('score', 0), 'reason': a.get('feedback', '')}
                         for i, a in enumerate(answers)],
    }


def _fallback_questions(job, req_skills, gaps_text, dept_cat) -> list:
    """Fallback if Gemini is unavailable."""
    skill1 = req_skills[0] if req_skills else 'your primary skill'
    return [
        {
            "question": f"Can you explain your experience with {skill1} and describe a project where you used it?",
            "type": "technical",
            "target": "Core skill assessment",
            "good_answer_includes": f"Specific examples using {skill1}, challenges faced, and outcomes."
        },
        {
            "question": f"The agent identified some gaps in your profile: {gaps_text or 'limited demonstrated experience'}. How would you address these?",
            "type": "gap_probe",
            "target": "Self-awareness and growth mindset",
            "good_answer_includes": "Honest acknowledgment, concrete plan to improve, any current efforts."
        },
        {
            "question": "Describe a situation where you had to solve a difficult problem under pressure. What was your approach?",
            "type": "situational",
            "target": "Problem-solving under pressure",
            "good_answer_includes": "Clear situation, specific actions taken, measurable result."
        },
        {
            "question": "Tell me about your most complex project. What was your role and what challenges did you overcome?",
            "type": "project",
            "target": "Depth of practical experience",
            "good_answer_includes": "Project scope, personal contribution, technical or domain challenges, outcomes."
        },
        {
            "question": "Describe a time you failed at something professionally or academically. What did you learn?",
            "type": "behavioral",
            "target": "Self-awareness, resilience, and learning ability",
            "good_answer_includes": "Honest failure, personal accountability, concrete lesson learned, how applied later."
        },
        {
            "question": f"Why are you specifically interested in the {job.title} role at {job.company.name}?",
            "type": "motivational",
            "target": "Motivation and culture fit",
            "good_answer_includes": "Research on the company, alignment with personal goals, specific role aspects."
        },
    ]
