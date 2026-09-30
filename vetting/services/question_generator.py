import json
import random
from core.utils.llm_client import llm_generate as _llm_generate

# Variety seeds so Gemini never generates the same question
_VARIETY_SEEDS = [
    "Focus on edge cases and real-world messy input.",
    "Use a business data scenario involving transactions.",
    "Base it on a social media or analytics context.",
    "Use a file/text processing scenario.",
    "Focus on algorithm efficiency and optimisation.",
    "Use an e-commerce or inventory management context.",
    "Use a healthcare or patient-data processing scenario.",
    "Focus on string manipulation and parsing.",
    "Use a logistics or delivery tracking scenario.",
    "Use a financial calculations scenario.",
]

_SENIORITY_HINTS = {
    'junior':  'Entry-level. Questions should test fundamentals, not advanced edge cases. Expect 0–1 years experience.',
    'mid':     'Mid-level. Questions should require solid practical understanding. Expect 2–4 years experience.',
    'senior':  'Senior-level. Questions should test deep expertise, trade-offs, and architectural thinking. Expect 5+ years.',
    'intern':  'Internship. Very basic questions; test core concepts only.',
    'any':     'Any level. Moderate difficulty.',
}

_DEPT_LABEL = {
    'tech':        'Technology / Software Engineering',
    'engineering': 'Engineering (EEE / Mechanical / Civil)',
    'business':    'Business / MBA / Marketing / Finance',
    'design':      'Design / UI-UX / Creative Arts / Architecture',
    'science':     'Science / Research / Mathematics / Statistics',
    'humanities':  'Humanities / Journalism / Economics / Media',
    'any':         'General',
}


def _build_context_block(job, department_category, topic, keywords, seniority,
                          custom_instructions):
    """Build the shared context section inserted into every prompt."""
    dept_label = _DEPT_LABEL.get(department_category, 'General')
    seniority_hint = _SENIORITY_HINTS.get(seniority, _SENIORITY_HINTS['any'])
    skills = [s.name for s in job.required_skills.all()]
    skills_str = ', '.join(skills) if skills else '(see job title)'

    kw_line = f"Keywords / Subtopics to cover: {keywords}" if keywords else ''
    ci_line = f"Special company instructions: {custom_instructions}" if custom_instructions else ''
    topic_line = f"PRIMARY TOPIC (most important — build the entire assessment around this): {topic}" if topic else ''

    parts = [
        f"Job Title       : {job.title}",
        f"Company         : {job.company.name if hasattr(job, 'company') else ''}",
        f"Department      : {dept_label}",
        f"Required Skills : {skills_str}",
        f"Seniority       : {seniority} — {seniority_hint}",
    ]
    if topic_line:   parts.append(topic_line)
    if kw_line:      parts.append(kw_line)
    if ci_line:      parts.append(ci_line)
    return '\n'.join(parts)


class QuestionGenerator:
    """
    Generate assessments using Gemini AI.

    Params shared by all generate_* methods:
        topic              — main subject the company wants tested (e.g. 'Django REST APIs')
        keywords           — comma-separated subtopics (e.g. 'serializers, permissions, JWT')
        seniority          — 'intern' | 'junior' | 'mid' | 'senior' | 'any'
        custom_instructions— free-text company instructions (e.g. 'Avoid theoretical Qs')
        mcq_count          — number of MCQ questions (mcq_written only, default 4)
        written_count      — number of written questions (mcq_written only, default 2)
    """

    def __init__(self):
        self.model = 'gemini-2.5-flash-lite'

    # ------------------------------------------------------------------
    # CODING CHALLENGE
    # ------------------------------------------------------------------
    def generate_challenge(self, job, difficulty='medium',
                           department_category='tech',
                           topic='', keywords='',
                           seniority='any', custom_instructions='',
                           # legacy alias kept for backward compat
                           topic_focus=''):
        if not topic:
            topic = topic_focus  # backward compat

        ctx = _build_context_block(job, department_category, topic, keywords,
                                   seniority, custom_instructions)
        variety = random.choice(_VARIETY_SEEDS)

        prompt = f"""
You are a world-class technical interviewer. Generate ONE unique, specific coding challenge.

=== ASSESSMENT CONTEXT ===
{ctx}
Difficulty      : {difficulty} (easy ≈ 30 min, medium ≈ 45 min, hard ≈ 60 min)
Scenario seed   : {variety}

=== OUTPUT FORMAT ===
Return ONLY a raw JSON object — no markdown, no code fences.

{{
  "title": "Specific challenge title directly related to the topic",
  "description": "Detailed real-world problem statement. Include a concrete scenario, clear input/output spec, and 2 worked examples. Must be directly about: {topic or job.title}",
  "starter_code": "Python function template with type hints, docstring, and TODO",
  "test_cases": [
    {{"input": "exact stdin string", "expected": "exact stdout string", "is_public": true}},
    {{"input": "...", "expected": "...", "is_public": true}},
    {{"input": "edge case", "expected": "...", "is_public": false}},
    {{"input": "another hidden", "expected": "...", "is_public": false}}
  ],
  "skill_tags": ["tag1", "tag2"],
  "language": "python",
  "hints": ["hint1", "hint2"]
}}

=== STRICT RULES ===
- The challenge MUST be about "{topic or job.title}" — do not generate a generic sorting/filtering problem
- test_case input/expected must be plain strings matching Python stdin/stdout
- If keywords are given ({keywords}), at least one question aspect must touch each keyword
- If company instructions are given, follow them exactly
"""

        return self._call_gemini(prompt, ['title', 'description', 'starter_code', 'test_cases'],
                                 lambda: self._fallback_coding(job, topic or job.title, difficulty))

    # ------------------------------------------------------------------
    # MCQ + WRITTEN
    # ------------------------------------------------------------------
    def generate_mcq_written(self, job, difficulty='medium',
                              department_category='business',
                              topic='', keywords='',
                              seniority='any', custom_instructions='',
                              mcq_count=4, written_count=2,
                              # legacy alias
                              topic_focus=''):
        if not topic:
            topic = topic_focus

        mcq_count   = max(2, min(int(mcq_count), 8))
        written_count = max(1, min(int(written_count), 4))

        ctx = _build_context_block(job, department_category, topic, keywords,
                                   seniority, custom_instructions)
        variety = random.choice(_VARIETY_SEEDS)
        dept_label = _DEPT_LABEL.get(department_category, 'General')

        # Build MCQ template lines
        mcq_templates = '\n'.join([
            f'''    {{
      "id": {i+1}, "type": "mcq",
      "question": "Specific MCQ question #{i+1} directly about {topic or dept_label}",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "A",
      "explanation": "Why A is correct",
      "points": 10
    }}''' for i in range(mcq_count)
        ])
        written_templates = '\n'.join([
            f'''    {{
      "id": {mcq_count+j+1}, "type": "written",
      "question": "Open-ended scenario question #{j+1} requiring 100-200 words. Must be practical and specific to {topic or dept_label}.",
      "word_limit": 200,
      "grading_rubric": "Key points the answer must cover",
      "points": {30 if j == 0 else 20}
    }}''' for j in range(written_count)
        ])

        prompt = f"""
You are a world-class assessor for {dept_label} roles. Generate a UNIQUE, TOPIC-SPECIFIC assessment.

=== ASSESSMENT CONTEXT ===
{ctx}
Difficulty      : {difficulty}
Scenario seed   : {variety}
MCQ questions   : {mcq_count}
Written questions: {written_count}

=== CRITICAL REQUIREMENT ===
The ENTIRE assessment must be built around the topic: "{topic or dept_label}"
Every single question must test knowledge of this specific topic.
{"Keywords to cover (distribute across questions): " + keywords if keywords else ""}
{"Company special instructions: " + custom_instructions if custom_instructions else ""}

=== OUTPUT FORMAT ===
Return ONLY a raw JSON object — no markdown, no code fences.

{{
  "title": "Assessment title that names the topic explicitly",
  "instructions": "2-3 sentence instructions for the candidate explaining what this assessment covers",
  "questions": [
{mcq_templates},
{written_templates}
  ]
}}

=== STRICT RULES ===
- All {mcq_count} MCQs must be about "{topic or dept_label}" — no generic business/communication questions
- All {written_count} written questions must require practical application of "{topic or dept_label}"
- MCQ options must be plausible — wrong answers should be common misconceptions, not obviously silly
- Written questions: test real-world judgment and application, not text-book recall
- If seniority is senior/mid, questions should require experience, not just definitions
- No duplicate question styles across the paper
"""

        return self._call_gemini(prompt, ['title', 'instructions', 'questions'],
                                 lambda: self._fallback_mcq(job, dept_label,
                                                             topic or job.title,
                                                             mcq_count, written_count))

    # ------------------------------------------------------------------
    # AI GRADING for written answers
    # ------------------------------------------------------------------
    def grade_written_answer(self, question, rubric, answer, max_points=20):
        prompt = f"""
You are a fair, experienced examiner. Grade the following written answer.

Question    : {question}
Rubric      : {rubric}
Answer      : {answer}
Max points  : {max_points}

Return ONLY raw JSON:
{{
  "score": <integer 0–{max_points}>,
  "feedback": "2-3 sentence feedback",
  "strengths": ["strength1"],
  "improvements": ["suggestion1"]
}}
"""
        try:
            text = self._clean(_llm_generate(prompt))
            result = json.loads(text)
            return {
                'score': max(0, min(int(result.get('score', 0)), max_points)),
                'feedback': result.get('feedback', ''),
                'strengths': result.get('strengths', []),
                'improvements': result.get('improvements', []),
            }
        except Exception as e:
            print(f'[QGen] Written grading failed (Gemini + Ollama): {e}')
            return {'score': max_points // 2, 'feedback': 'Auto-graded (AI unavailable)',
                    'strengths': [], 'improvements': []}

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------
    def _call_gemini(self, prompt, required_keys, fallback_fn):
        """Try Gemini (with cascade) then Ollama; use fallback_fn if both fail."""
        try:
            text = self._clean(_llm_generate(prompt))
            data = json.loads(text)
            for k in required_keys:
                if k not in data:
                    raise ValueError(f'Missing key: {k}')
            print(f'[QGen] Generated successfully: {data.get("title")}')
            return data
        except Exception as e:
            print(f'[QGen] All LLM backends failed ({e}) — using fallback')
            return fallback_fn()

    @staticmethod
    def _clean(text):
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]
        return text.strip()

    # ------------------------------------------------------------------
    # FALLBACKS
    # ------------------------------------------------------------------
    def _fallback_coding(self, job, topic, difficulty):
        return {
            'title': f'Data Processing Challenge — {topic}',
            'description': (
                f'Implement `process_data(records: list, query: str) -> dict` '
                f'that filters and aggregates records based on the query string.\n\n'
                f'Example:\n'
                f'Input: records=[{{"name":"A","score":90}},{{"name":"B","score":60}}], query="score>70"\n'
                f'Output: {{"results":[{{"name":"A","score":90}}],"count":1,"avg":90.0}}'
            ),
            'starter_code': (
                'from typing import List, Dict, Any\n\n'
                'def process_data(records: List[Dict], query: str) -> Dict:\n'
                '    """\n'
                '    Filter and aggregate records.\n'
                '    query format: "field>value" or "field==value"\n'
                '    """\n'
                '    # TODO: implement\n'
                '    pass'
            ),
            'test_cases': [
                {'input': '[{"name":"A","score":90},{"name":"B","score":60}]\nscore>70',
                 'expected': '{"results": [{"name": "A", "score": 90}], "count": 1, "avg": 90.0}',
                 'is_public': True},
                {'input': '[{"name":"X","val":5},{"name":"Y","val":10}]\nval==10',
                 'expected': '{"results": [{"name": "Y", "val": 10}], "count": 1, "avg": 10.0}',
                 'is_public': False},
            ],
            'skill_tags': ['python', 'data-processing', topic.lower().replace(' ', '-')],
            'language': 'python',
            'hints': ['Parse the query string to extract field, operator, value',
                      'Use a loop to filter records before aggregating'],
        }

    def _fallback_mcq(self, job, dept_label, topic, mcq_count=4, written_count=2):
        # Pre-built varied question bank so each slot is different
        _bank = [
            {
                'question': f'What is the primary purpose of {topic} in a professional context?',
                'options': [
                    f'A. To streamline and improve outcomes in {topic}-related workflows',
                    f'B. To replace all manual processes in an organisation',
                    f'C. To eliminate the need for domain expertise',
                    f'D. To reduce the number of tools used',
                ],
                'correct_answer': 'A',
                'explanation': f'{topic} is primarily used to improve efficiency and outcomes in its domain.',
            },
            {
                'question': f'Which of the following is a best practice when working with {topic}?',
                'options': [
                    f'A. Ignoring edge cases and focusing only on the happy path',
                    f'B. Documenting decisions and maintaining version control',
                    f'C. Skipping testing to deliver faster',
                    f'D. Working without feedback loops',
                ],
                'correct_answer': 'B',
                'explanation': 'Documentation and version control are universal best practices.',
            },
            {
                'question': f'What is a common challenge when implementing {topic} in production?',
                'options': [
                    f'A. Scalability and handling unexpected load',
                    f'B. Writing the initial code',
                    f'C. Naming variables correctly',
                    f'D. Setting up a local development environment',
                ],
                'correct_answer': 'A',
                'explanation': 'Scalability is a frequent real-world concern once a solution reaches production.',
            },
            {
                'question': f'How should errors and exceptions be handled in a {topic} system?',
                'options': [
                    f'A. Catch all exceptions silently and continue',
                    f'B. Log them and display generic messages to users while handling root causes',
                    f'C. Show raw stack traces to end users for transparency',
                    f'D. Restart the system on every error',
                ],
                'correct_answer': 'B',
                'explanation': 'Good error handling means logging internally and giving users safe, helpful messages.',
            },
            {
                'question': f'Which metric is most useful for evaluating the quality of a {topic} solution?',
                'options': [
                    f'A. Lines of code written',
                    f'B. Number of meetings held',
                    f'C. Measurable outcome improvement (speed, accuracy, cost, uptime)',
                    f'D. Team size',
                ],
                'correct_answer': 'C',
                'explanation': 'Quality is best measured by concrete, measurable improvements to key outcomes.',
            },
            {
                'question': f'When collaborating on a {topic} project, what is critical for team success?',
                'options': [
                    f'A. Each person working in isolation to avoid conflicts',
                    f'B. Clear communication, shared standards, and regular code/design reviews',
                    f'C. The most senior person making all decisions alone',
                    f'D. Avoiding documentation to save time',
                ],
                'correct_answer': 'B',
                'explanation': 'Collaboration requires shared standards, open communication, and peer review.',
            },
            {
                'question': f'How would you approach debugging a complex issue in a {topic} system?',
                'options': [
                    f'A. Restart everything and hope it resolves',
                    f'B. Isolate the problem, reproduce it, analyse logs, then test a fix systematically',
                    f'C. Ask someone else to fix it without investigating',
                    f'D. Rewrite the entire module from scratch immediately',
                ],
                'correct_answer': 'B',
                'explanation': 'Systematic debugging — isolate, reproduce, analyse, fix, verify — is the professional approach.',
            },
            {
                'question': f'What role does testing play in a {topic} project?',
                'options': [
                    f'A. Testing is optional if the developer is confident',
                    f'B. Testing validates correctness, prevents regressions, and builds confidence to deploy',
                    f'C. Testing only matters for large teams',
                    f'D. Testing slows down delivery and should be skipped in deadlines',
                ],
                'correct_answer': 'B',
                'explanation': 'Testing is essential at all scales to prevent bugs and enable confident iteration.',
            },
        ]
        # Cycle through the bank, wrapping if mcq_count > bank size
        mcqs = []
        for i in range(mcq_count):
            entry = _bank[i % len(_bank)]
            mcqs.append({
                'id': i + 1,
                'type': 'mcq',
                'question': entry['question'],
                'options': entry['options'],
                'correct_answer': entry['correct_answer'],
                'explanation': entry['explanation'],
                'points': 10,
            })

        written = [
            {
                'id': mcq_count + 1, 'type': 'written',
                'question': f'Describe a real scenario where you applied skills related to {topic}. '
                            f'What was the problem, what did you do, and what was the outcome? (100-200 words)',
                'word_limit': 200,
                'grading_rubric': f'Specific scenario, clear problem statement, concrete actions, measurable outcome related to {topic}',
                'points': 30,
            },
        ]
        if written_count >= 2:
            written.append({
                'id': mcq_count + 2, 'type': 'written',
                'question': f'As a {job.title}, how would you prioritise tasks related to {topic} '
                            f'under tight deadlines? Give a specific example. (100-150 words)',
                'word_limit': 150,
                'grading_rubric': 'Clear prioritisation framework, specific example, outcome-focused answer',
                'points': 20,
            })
        return {
            'title': f'{topic} Assessment — {job.title}',
            'instructions': f'This assessment tests your knowledge of {topic}. '
                            f'Answer all MCQs carefully and provide detailed written responses.',
            'questions': mcqs + written[:written_count],
        }
