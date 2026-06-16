"""
Recruitment Agent — 7-step agentic screening loop
===================================================
Runs autonomously when a candidate applies or when a company triggers a re-run.

Step 1  🔍  Gather candidate profile
Step 2  📋  Analyse job requirements
Step 3  🧮  Compute feature scores  (skills, CGPA, projects, activity, trust)
Step 4  ⚖️   Apply RL-learned weights
Step 5  🎯  Make shortlist / reject / review decision
Step 6  📊  Generate fit report (strengths, gaps, recommendation)
Step 7  ✅  Auto-update application status
"""

import traceback
from datetime import datetime

# ── Skill ecosystem map ───────────────────────────────────────────────────────
# If a job requires a parent language/platform, these child skills also count
# as partial evidence for that requirement.
# Example: job requires "python" → student with "tensorflow" gets partial credit
# because tensorflow IS a Python library.
SKILL_ECOSYSTEM = {
    'python': [
        'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'sklearn',
        'pandas', 'numpy', 'scipy', 'matplotlib', 'seaborn', 'plotly',
        'django', 'flask', 'fastapi', 'streamlit', 'gradio',
        'opencv', 'cv2', 'pillow', 'pil',
        'huggingface', 'transformers', 'langchain', 'openai',
        'jupyter', 'anaconda', 'conda',
        'sqlalchemy', 'alembic', 'celery', 'redis',
        'pytest', 'unittest', 'pydantic',
        'ml', 'deep learning', 'machine learning', 'nlp', 'computer vision',
        'data science', 'data analysis',
    ],
    'javascript': [
        'react', 'vue', 'angular', 'svelte', 'next.js', 'nuxt',
        'node', 'node.js', 'express', 'nestjs', 'koa',
        'typescript', 'jquery', 'webpack', 'vite', 'babel',
        'redux', 'mobx', 'graphql', 'apollo',
    ],
    'java': [
        'spring', 'spring boot', 'springboot', 'hibernate', 'jpa',
        'maven', 'gradle', 'junit', 'kotlin', 'android',
    ],
    'c++': [
        'qt', 'boost', 'cmake', 'cuda', 'opengl', 'directx',
        'unreal engine', 'ue4', 'ue5',
    ],
    'c#': [
        '.net', 'asp.net', 'unity', 'wpf', 'xamarin', 'blazor',
        'entity framework', 'linq',
    ],
    'php': [
        'laravel', 'symfony', 'wordpress', 'codeigniter', 'yii',
        'composer', 'magento',
    ],
    'ruby': ['rails', 'ruby on rails', 'sinatra', 'rspec'],
    'go':   ['gin', 'echo', 'fiber', 'gorm', 'grpc'],
    'rust': ['actix', 'tokio', 'rocket', 'wasm'],
    'swift': ['ios', 'xcode', 'swiftui', 'uikit', 'cocoa'],
    'kotlin': ['android', 'jetpack compose', 'coroutines', 'ktor'],
    'dart':   ['flutter'],
    'r':      ['ggplot', 'dplyr', 'tidyverse', 'shiny', 'caret'],
    'sql': [
        'mysql', 'postgresql', 'postgres', 'sqlite', 'mssql',
        'oracle', 'mariadb', 'redshift', 'snowflake', 'bigquery',
    ],
    'machine learning': [
        'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'sklearn',
        'xgboost', 'lightgbm', 'catboost', 'ml', 'deep learning',
        'neural network', 'cnn', 'rnn', 'lstm', 'transformer',
        'nlp', 'computer vision', 'reinforcement learning',
    ],
    'deep learning': [
        'tensorflow', 'pytorch', 'keras', 'neural network',
        'cnn', 'rnn', 'lstm', 'gpt', 'bert', 'transformer',
    ],
    'data science': [
        'pandas', 'numpy', 'matplotlib', 'seaborn', 'jupyter',
        'scikit-learn', 'sklearn', 'statistics', 'data analysis',
        'tableau', 'power bi', 'excel',
    ],
    'devops': [
        'docker', 'kubernetes', 'k8s', 'jenkins', 'github actions',
        'ci/cd', 'terraform', 'ansible', 'aws', 'gcp', 'azure',
        'linux', 'bash', 'nginx', 'apache',
    ],
    'cloud': [
        'aws', 'gcp', 'azure', 'heroku', 'vercel', 'netlify',
        'lambda', 's3', 'ec2', 'rds', 'firebase',
    ],
}

# Reverse map: child → parent(s)  (e.g. tensorflow → python, machine learning)
_CHILD_TO_PARENTS = {}
for _parent, _children in SKILL_ECOSYSTEM.items():
    for _child in _children:
        _CHILD_TO_PARENTS.setdefault(_child, set()).add(_parent)


def expand_skill_set(skills: set) -> set:
    """
    Given a set of required skill names (lowercase), expand it to include
    all child/related skills from SKILL_ECOSYSTEM.
    e.g. {'python'} → {'python', 'tensorflow', 'pytorch', 'django', ...}
    """
    expanded = set(skills)
    for skill in skills:
        expanded.update(SKILL_ECOSYSTEM.get(skill, []))
    return expanded


def parent_skills_of(skill_name: str) -> set:
    """
    Return parent skills that the given child skill implies.
    e.g. 'tensorflow' → {'python', 'machine learning'}
    """
    return _CHILD_TO_PARENTS.get(skill_name.lower(), set())


class RecruitmentAgent:
    SHORTLIST_THRESHOLD = 0.60   # weighted score ≥ 0.60 → shortlist
    REVIEW_THRESHOLD    = 0.45   # 0.45–0.60 → manual review; < 0.45 → reject

    def __init__(self, company):
        self.company = company
        self.steps   = []

    # ── internal log helper ───────────────────────────────────────────────────

    def _log(self, step_num, action, thought, result, data=None):
        self.steps.append({
            'step':      step_num,
            'action':    action,
            'thought':   thought,
            'result':    result,
            'data':      data or {},
            'timestamp': datetime.now().strftime('%H:%M:%S'),
        })

    # ── step 1: gather candidate ──────────────────────────────────────────────

    def _step1_gather_candidate(self, student):
        from core.models import StudentSkill
        from vetting.models import VettingResult

        skill_objs   = list(StudentSkill.objects.filter(student=student).select_related('skill'))
        skill_names  = [ss.skill.name for ss in skill_objs]

        # Build vetting evidence map: skill_name_lower → best VettingResult score (0–100)
        # IMPORTANT: Only count vetting tests from THIS company's challenges.
        # A test taken for Company A must not affect Company B's evaluation of the same student.
        # VettingChallenge → Job → Company, so we filter by challenge__job__company.
        vetting_scores = {}   # e.g. {'python': 87.5, 'django': 65.0}
        try:
            results = (VettingResult.objects
                       .filter(
                           session__student=student,
                           session__challenge__job__company=self.company,  # ← company-scoped
                       )
                       .select_related('session__challenge'))
            for vr in results:
                # Skip unsubmitted / incomplete sessions — final_score is None
                # means the student opened the test but never submitted answers.
                # Treating None as 0 would unfairly penalise them.
                if vr.final_score is None:
                    continue
                skill_tags = vr.session.challenge.skill_tags or []
                for tag in skill_tags:
                    tag_lower = tag.lower()
                    score = float(vr.final_score)
                    if tag_lower not in vetting_scores or score > vetting_scores[tag_lower]:
                        vetting_scores[tag_lower] = score
        except Exception:
            pass  # vetting app may not have data yet — degrade gracefully

        # Rich skill data: name → {proficiency, cross_validated, vetting_score}
        skill_detail = {
            ss.skill.name.lower(): {
                'proficiency':     ss.proficiency_level,   # Beginner / Intermediate / Expert
                'cross_validated': ss.cross_validated,
                'vetting_score':   vetting_scores.get(ss.skill.name.lower()),  # None if never tested
            }
            for ss in skill_objs
        }
        projects = list(student.projects.prefetch_related('tech_stack').all())
        cgpa     = float(student.cgpa or 0)

        self._log(
            1,
            '🔍 Gather Candidate Profile',
            f"Loading profile for {student.name} from the database…",
            (
                f"Found: {student.name} | Dept: {student.department} | "
                f"CGPA: {cgpa or 'N/A'} | Skills: {', '.join(skill_names[:6]) or 'none listed'} | "
                f"Projects: {len(projects)} | LinkedIn: {student.linkedin_score} | "
                f"GitHub: {student.github_score}"
            ),
            {
                'name':           student.name,
                'department':     student.department,
                'cgpa':           cgpa,
                'skills':         skill_names,
                'skill_detail':   skill_detail,
                'vetting_scores': vetting_scores,
                'project_count':  len(projects),
                'has_resume':     bool(student.resume),
                # ⚠️ Do NOT put ORM objects here — this dict is stored as JSON in reasoning_steps
                'linkedin_score': student.linkedin_score,
                'github_score':   student.github_score,
                'trust_score':    float(student.trust_score or 0),
                'activity_score': float(student.activity_score or 0),
            }
        )
        return {
            'skills':         skill_names,
            'skill_detail':   skill_detail,
            'vetting_scores': vetting_scores,
            'cgpa':           cgpa,
            'project_count':  len(projects),
            'projects':       projects,   # ORM objects — used only in step 3, never serialized to JSON
            'has_resume':     bool(student.resume),  # True if student uploaded a CV
            'linkedin_score': student.linkedin_score,
            'github_score':   student.github_score,
            'trust_score':    float(student.trust_score or 0),
            'activity_score': float(student.activity_score or 0),
        }

    # ── step 2: analyse job ───────────────────────────────────────────────────

    def _step2_analyse_job(self, job):
        req_skills = [s.name for s in job.required_skills.all()]
        min_cgpa   = float(job.min_cgpa or 0)

        self._log(
            2,
            '📋 Analyse Job Requirements',
            f'Reading specification for "{job.title}" at {job.company.name}…',
            (
                f"Title: {job.title} | Type: {job.job_type} | "
                f"Required skills: {', '.join(req_skills) or 'not specified'} | "
                f"Min CGPA: {min_cgpa or 'not set'}"
            ),
            {
                'title':      job.title,
                'company':    job.company.name,
                'req_skills': req_skills,
                'min_cgpa':   min_cgpa,
                'job_type':   job.job_type,
                'department': job.department_category,
            }
        )
        return {'req_skills': req_skills, 'min_cgpa': min_cgpa}

    # ── step 3: score features ────────────────────────────────────────────────

    def _step3_compute_scores(self, candidate_data, job_data):
        # ── Proficiency multipliers ───────────────────────────────────────────
        PROFICIENCY = {'Beginner': 0.50, 'Intermediate': 0.75, 'Expert': 1.00}

        req          = [s.lower() for s in job_data['req_skills']]
        skill_detail = candidate_data.get('skill_detail', {})   # name → {proficiency, cross_validated}
        cand_names   = list(skill_detail.keys())                 # already lowercased in step 1

        # ── Skills: evidence-based scoring ───────────────────────────────────
        #
        # Priority order (highest wins):
        #  1. Vetting test passed (≥70%)  → score = vetting_score/100  (VERIFIED — most trusted)
        #  2. Vetting test attempted (<70%)→ score = vetting_score/100 * 0.85 (tested but didn't pass)
        #  3. Self-report Expert + cross-validated → 0.72 (stated+verified via 2 sources)
        #  4. Self-report Expert only      → 0.60  (stated, not verified)
        #  5. Self-report Intermediate + cross-validated → 0.55
        #  6. Self-report Intermediate only → 0.45
        #  7. Self-report Beginner         → 0.30
        #  8. No match at all              → 0.00
        #
        # Why cap self-report? Anyone can claim "Expert". Vetting test is objective proof.

        SELF_REPORT_SCORES = {
            ('Expert',       True):  0.72,   # Expert + CV&LinkedIn both confirm
            ('Expert',       False): 0.60,   # Expert but only self-claimed
            ('Intermediate', True):  0.55,   # Intermediate + cross-validated
            ('Intermediate', False): 0.45,   # Intermediate, self-claimed only
            ('Beginner',     True):  0.35,
            ('Beginner',     False): 0.30,
        }

        vetting_scores = candidate_data.get('vetting_scores', {})

        # ── Project-implied skills ────────────────────────────────────────────
        # If a student's projects use a technology but it's not in their explicit
        # skill list, infer it as evidence. This helps students who list projects
        # with "tensorflow" tech_stack but never explicitly added that skill.
        # Confidence: 3+ projects using the tech → Intermediate; 1-2 → Beginner.
        projects_for_inference = candidate_data.get('projects', [])
        implied_skill_counts = {}  # tech_name_lower → count of projects using it
        for _p in projects_for_inference:
            for _tech in _p.tech_stack.all():
                _t = _tech.name.lower()
                implied_skill_counts[_t] = implied_skill_counts.get(_t, 0) + 1

        # Merge implied skills into skill_detail (only where not already explicit)
        for _tech, _count in implied_skill_counts.items():
            if _tech not in skill_detail:
                _prof = 'Intermediate' if _count >= 3 else 'Beginner'
                skill_detail[_tech] = {
                    'proficiency':     _prof,
                    'cross_validated': False,
                    'vetting_score':   None,
                    'implied':         True,   # flag: not explicitly stated
                }
        cand_names = list(skill_detail.keys())  # refresh after merging implied skills

        if req:
            matched_count = 0
            total_skill_score = 0.0
            skill_notes = []

            for r in req:
                best       = 0.0
                best_label = 'missing'

                # ── Direct match: candidate has this exact skill (or substring) ──
                for cname in cand_names:
                    if r not in cname and cname not in r:
                        continue

                    info    = skill_detail[cname]
                    implied = info.get('implied', False)
                    v_score = vetting_scores.get(cname)   # None if never tested

                    if v_score is not None:
                        raw        = v_score / 100.0
                        test_score = raw if v_score >= 70 else raw * 0.85
                        # Floor: a failed test shouldn't erase all self-report evidence.
                        # If the student has self-reported proficiency, their floor is
                        # 55% of their normal self-report score (giving some credit even
                        # when they failed the test — they still attempted it).
                        key        = (info['proficiency'], info.get('cross_validated', False))
                        self_floor = SELF_REPORT_SCORES.get(key, 0.30) * 0.55
                        candidate_score = max(test_score, self_floor)
                        label = f"tested({v_score:.0f}%{'✓' if v_score >= 70 else ''})"
                    elif implied:
                        # Implied from project tech_stack — lower confidence than explicit
                        key = (info['proficiency'], False)
                        candidate_score = SELF_REPORT_SCORES.get(key, 0.30) * 0.65
                        label = f"proj-implied({info['proficiency']})"
                    else:
                        key = (info['proficiency'], info['cross_validated'])
                        candidate_score = SELF_REPORT_SCORES.get(key, 0.40)
                        label = f"self({info['proficiency']}{'✓cv' if info['cross_validated'] else ''})"

                    if candidate_score > best:
                        best       = candidate_score
                        best_label = f"{cname}→{label}={candidate_score*100:.0f}%"

                # ── Ecosystem match: candidate has a child skill that implies r ──
                # e.g. job needs "python", student has "tensorflow" → partial credit
                # This is capped at 0.75 × direct score to avoid overstating fit.
                # (knowing tensorflow implies python but doesn't prove python mastery)
                if best == 0.0:
                    child_skills = SKILL_ECOSYSTEM.get(r, [])
                    for cname in cand_names:
                        if cname not in child_skills:
                            continue
                        info    = skill_detail[cname]
                        implied = info.get('implied', False)
                        v_score = vetting_scores.get(cname)

                        if v_score is not None:
                            raw  = v_score / 100.0
                            base = raw if v_score >= 70 else raw * 0.85
                            label = f"via {cname}→tested({v_score:.0f}%)"
                        elif implied:
                            key  = (info['proficiency'], False)
                            base = SELF_REPORT_SCORES.get(key, 0.30) * 0.65
                            label = f"via {cname}→proj-implied({info['proficiency']})"
                        else:
                            key  = (info['proficiency'], info['cross_validated'])
                            base = SELF_REPORT_SCORES.get(key, 0.40)
                            label = f"via {cname}→self({info['proficiency']})"

                        # Ecosystem inference penalty: 75% of direct score
                        ecosystem_score = round(base * 0.75, 3)
                        if ecosystem_score > best:
                            best       = ecosystem_score
                            best_label = f"{r}←{label}={ecosystem_score*100:.0f}%"

                if best > 0:
                    matched_count += 1
                    skill_notes.append(best_label)
                else:
                    skill_notes.append(f"{r}→missing")
                total_skill_score += best

            skills_score  = total_skill_score / len(req)
            skills_detail = f"{matched_count}/{len(req)} matched | " + ", ".join(skill_notes)
        else:
            skills_score  = 0.65
            skills_detail = "No skill requirements — defaulting to 65%"

        # ── CGPA: relative to minimum, not absolute 4.0 scale ────────────────
        # If min_cgpa is set:
        #   Below minimum  → scales from 0 to 0.50 (proportional penalty)
        #   Meets minimum  → 0.55 base
        #   Perfect 4.0    → 1.00
        # If no minimum: raw cgpa/4.0
        cgpa     = candidate_data['cgpa']
        min_cgpa = job_data['min_cgpa']
        if cgpa > 0:
            if min_cgpa and min_cgpa > 0:
                if cgpa < min_cgpa:
                    cgpa_score  = round((cgpa / min_cgpa) * 0.50, 3)
                    cgpa_detail = f"CGPA {cgpa:.2f} below minimum {min_cgpa:.2f} — scaled penalty ({cgpa_score*100:.0f}%)"
                else:
                    # Linear scale: meeting minimum = 0.55, perfect 4.0 = 1.00
                    above_range = 4.0 - min_cgpa
                    above_pct   = (cgpa - min_cgpa) / above_range if above_range > 0 else 1.0
                    cgpa_score  = round(0.55 + 0.45 * above_pct, 3)
                    cgpa_detail = f"CGPA {cgpa:.2f}/4.0 (min {min_cgpa:.1f}) → {cgpa_score*100:.0f}%"
            else:
                cgpa_score  = round(min(cgpa / 4.0, 1.0), 3)
                cgpa_detail = f"CGPA {cgpa:.2f}/4.0 (no minimum set)"
        else:
            cgpa_score  = 0.45
            cgpa_detail = "CGPA not provided — defaulting to 45%"

        # ── Projects: inferred relevance + inferred complexity + count ──────────
        #
        # We DO NOT trust self-reported complexity_score or tech_stack alone.
        # Instead we infer from objective signals in the project record:
        #
        # RELEVANCE (per project, 0.0–1.0):
        #   0.60 weight → tech_stack overlap with required skills (explicit field)
        #   0.40 weight → keyword match of req skills in title + description (text evidence)
        #   A project is "relevant" if inferred_relevance ≥ 0.30
        #
        # COMPLEXITY (per project, 0.0–1.0) — inferred from 4 signals:
        #   duration_weeks  (0–0.35) : longer = harder
        #   tech_stack count(0–0.25) : more technologies = more complex
        #   description len (0–0.20) : richer description = more real work
        #   public evidence (0–0.20) : github_url +0.10, live_url +0.10
        #
        # FINAL projects_score = 0.45×relevance + 0.30×count + 0.25×avg_complexity

        projects      = candidate_data.get('projects', [])
        pc            = len(projects)
        req_skill_set = set(r.lower() for r in job_data['req_skills'])

        # Expand req_skill_set with ecosystem children for project relevance.
        # e.g. job requires "python" → also match tensorflow, pytorch, django, etc.
        # This way ML projects tagged with "tensorflow" are correctly seen as Python-relevant.
        expanded_req_skills = expand_skill_set(req_skill_set)

        relevant_count    = 0
        total_relevance   = 0.0
        total_complexity  = 0.0
        project_notes     = []

        for p in projects:
            # ── Relevance ──────────────────────────────────────────────
            tech_names = set(s.name.lower() for s in p.tech_stack.all())
            text       = (p.title + ' ' + p.description).lower()

            # Per-required-skill coverage approach:
            # For each required skill, check if this project covers it via:
            #   1.0 → direct match in tech_stack (e.g. tech has "python")
            #   0.70 → ecosystem child in tech_stack (e.g. tech has "django" → implies python)
            #   0.30 → text mention of skill or its children in title/description
            #   0.00 → no evidence
            # Final relevance = average coverage across all required skills.
            # This avoids dividing by the large expanded set size (old bug).
            if req_skill_set:
                per_skill = []
                for r in req_skill_set:
                    r_children = set(SKILL_ECOSYSTEM.get(r, []))
                    if r in tech_names:
                        per_skill.append(1.0)
                    elif tech_names & r_children:
                        per_skill.append(0.70)   # django in project → python job gets credit
                    elif r in text or any(c in text for c in r_children if len(c) > 3):
                        per_skill.append(0.30)   # at least mentioned in description
                    else:
                        per_skill.append(0.0)
                inferred_relevance = sum(per_skill) / len(req_skill_set)
            else:
                inferred_relevance = 0.5   # no requirements → treat as neutral

            if inferred_relevance >= 0.30:
                relevant_count += 1
            total_relevance += inferred_relevance

            # ── Complexity (inferred) ───────────────────────────────────
            # duration_weeks signal (0–0.35)
            # If duration_weeks is not set (common for CV-only students), fall back to
            # complexity_score (1–5), which is AI-assessed by Gemini during CV parsing.
            weeks = p.duration_weeks or 0
            if   weeks >= 16: dur_c = 0.35
            elif weeks >= 8:  dur_c = 0.25
            elif weeks >= 4:  dur_c = 0.18
            elif weeks >= 2:  dur_c = 0.10
            elif weeks >= 1:  dur_c = 0.05
            else:
                # No duration set — use Gemini's AI complexity rating from CV parsing
                # complexity_score: 1=trivial, 2=simple, 3=moderate, 4=solid, 5=complex
                # Map 1–5 → 0.0–0.25 (capped below full credit; objective signals > AI inference)
                gemini_c = int(getattr(p, 'complexity_score', 1) or 1)
                dur_c = round((gemini_c - 1) / 4.0 * 0.25, 3)

            # tech_stack count signal (0–0.25)
            tc     = len(tech_names)
            tech_c = min(tc * 0.05, 0.25)   # 1 tech=0.05, 5+=0.25

            # description richness signal (0–0.20)
            word_count = len(p.description.split()) if p.description else 0
            if   word_count >= 100: desc_c = 0.20
            elif word_count >= 50:  desc_c = 0.14
            elif word_count >= 20:  desc_c = 0.08
            else:                   desc_c = 0.02   # short/no description

            # public evidence signal (0–0.20)
            # If neither URL is set but the student uploaded a CV, the project existence
            # is confirmed by a real document — give a small base credit (0.05).
            has_resume = candidate_data.get('has_resume', False)
            pub_c = (0.10 if p.github_url else 0.0) + (0.10 if p.live_url else 0.0)
            if pub_c == 0.0 and has_resume:
                pub_c = 0.05   # CV-verified: project exists in uploaded document

            inferred_complexity = min(dur_c + tech_c + desc_c + pub_c, 1.0)

            # Small boost if project is verified by platform
            if p.verified:
                inferred_complexity = min(inferred_complexity + 0.05, 1.0)

            total_complexity += inferred_complexity
            project_notes.append(
                f"{p.title[:20]}: rel={inferred_relevance*100:.0f}% "
                f"cplx={inferred_complexity*100:.0f}%"
                f"({'github' if p.github_url else ''}{'live' if p.live_url else ''})"
            )

        avg_relevance  = (total_relevance  / pc) if pc > 0 else 0.0
        avg_complexity = (total_complexity / pc) if pc > 0 else 0.0
        count_score    = min(pc / 8.0, 1.0)   # need 8 projects for full count score

        projects_score  = round(avg_relevance * 0.45 + count_score * 0.30 + avg_complexity * 0.25, 3)
        projects_detail = (
            f"{pc} projects | {relevant_count} relevant (≥30%) | "
            f"avg relevance {avg_relevance*100:.0f}% | avg complexity {avg_complexity*100:.0f}% | "
            + "; ".join(project_notes[:3]) + ("…" if pc > 3 else "")
        )

        # ── Activity: GitHub 60% + platform activity 40% ─────────────────────
        github_norm    = min(candidate_data['github_score'] / 100, 1.0)
        activity_raw   = candidate_data['activity_score']
        activity_score = round(github_norm * 0.6 + min(activity_raw / 100, 1.0) * 0.4, 3)
        activity_detail = f"GitHub: {candidate_data['github_score']} pts | Activity: {activity_raw:.0f}/100"

        # ── Trust: LinkedIn 50% + profile trust score 50% ────────────────────
        linkedin_norm = min(candidate_data['linkedin_score'] / 100, 1.0)
        trust_raw     = candidate_data['trust_score']
        trust_score   = round(linkedin_norm * 0.5 + min(trust_raw / 100, 1.0) * 0.5, 3)
        trust_detail  = f"LinkedIn: {candidate_data['linkedin_score']}/100 | Trust: {trust_raw:.0f}/100"

        scores = {
            'skills':   {'score': round(skills_score,   3), 'detail': skills_detail},
            'cgpa':     {'score': round(cgpa_score,     3), 'detail': cgpa_detail},
            'projects': {'score': round(projects_score, 3), 'detail': projects_detail},
            'activity': {'score': round(activity_score, 3), 'detail': activity_detail},
            'trust':    {'score': round(trust_score,    3), 'detail': trust_detail},
        }

        self._log(
            3,
            '🧮 Compute Feature Scores',
            "Scoring across 5 dimensions: skills (proficiency-weighted), CGPA, projects (relevance+count), activity, trust…",
            " | ".join(f"{k}: {v['score']*100:.0f}%" for k, v in scores.items()),
            {'scores': scores}
        )
        return scores

    # ── step 4: apply weights ─────────────────────────────────────────────────

    def _step4_apply_weights(self, feature_scores, job=None):
        weights  = self.company.get_weights()
        # Job-specific weights override company defaults (if set on the job posting)
        if job and job.custom_weights:
            weights = {**weights, **job.custom_weights}

        # ── Normalize weights so they always sum to 1.0 ──────────────────────
        # Prevents scores > 100% when user sets e.g. skills=55% but keeps
        # other defaults, making the total 115%.
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: round(v / total_weight, 6) for k, v in weights.items()}

        weighted = 0.0
        breakdown = {}

        for key, w in weights.items():
            raw_score = feature_scores.get(key, {}).get('score', 0)
            fs        = min(raw_score, 1.0)   # cap individual scores at 100%
            contrib   = round(fs * w, 4)
            breakdown[key] = {
                'score':        fs,
                'weight':       round(w, 4),
                'contribution': contrib,
                'detail':       feature_scores.get(key, {}).get('detail', ''),
            }
            weighted += contrib

        weighted = round(min(weighted, 1.0), 4)   # final cap — should never exceed 1.0 after normalization
        formula  = " + ".join(
            f"{k}({v['score']*100:.0f}%×{v['weight']*100:.0f}%)"
            for k, v in breakdown.items()
        )

        self._log(
            4,
            '⚖️ Apply RL-Learned Weights',
            "Multiplying each feature score by the company's learned weights…",
            f"Weighted score = {weighted*100:.1f}%   [{formula}]",
            {'weights': weights, 'breakdown': breakdown, 'weighted_score': weighted}
        )
        return weighted, breakdown, weights

    # ── step 5: decide ────────────────────────────────────────────────────────

    def _step5_decide(self, weighted_score):
        if weighted_score >= self.SHORTLIST_THRESHOLD:
            decision   = 'shortlist'
            confidence = 'HIGH' if weighted_score >= 0.75 else 'MEDIUM'
            reasoning  = (
                f"Score {weighted_score*100:.1f}% ≥ shortlist threshold "
                f"{self.SHORTLIST_THRESHOLD*100:.0f}% → SHORTLIST ({confidence} confidence)"
            )
        elif weighted_score >= self.REVIEW_THRESHOLD:
            decision   = 'review'
            confidence = 'LOW'
            reasoning  = (
                f"Score {weighted_score*100:.1f}% is in the grey zone "
                f"({self.REVIEW_THRESHOLD*100:.0f}%–{self.SHORTLIST_THRESHOLD*100:.0f}%) "
                f"→ MANUAL REVIEW recommended"
            )
        else:
            decision   = 'reject'
            confidence = 'HIGH'
            reasoning  = (
                f"Score {weighted_score*100:.1f}% < reject threshold "
                f"{self.REVIEW_THRESHOLD*100:.0f}% → REJECT"
            )

        self._log(
            5,
            '🎯 Make Decision',
            (
                f"Comparing {weighted_score*100:.1f}% against thresholds: "
                f"shortlist ≥ {self.SHORTLIST_THRESHOLD*100:.0f}%, "
                f"reject < {self.REVIEW_THRESHOLD*100:.0f}%…"
            ),
            reasoning,
            {
                'score':               weighted_score,
                'decision':            decision,
                'confidence':          confidence,
                'shortlist_threshold': self.SHORTLIST_THRESHOLD,
                'review_threshold':    self.REVIEW_THRESHOLD,
            }
        )
        return decision, confidence

    # ── step 6: fit report ────────────────────────────────────────────────────

    def _step6_fit_report(self, student, job, feature_scores, weighted_score,
                          decision, breakdown, candidate_data, job_data):
        strengths, gaps = [], []

        for key, v in feature_scores.items():
            label = {
                'skills':   'Technical skill match',
                'cgpa':     'Academic performance',
                'projects': 'Project portfolio',
                'activity': 'GitHub / activity',
                'trust':    'LinkedIn & profile trust',
            }.get(key, key.capitalize())

            if v['score'] >= 0.75:
                strengths.append(f"{label}: {v['score']*100:.0f}% — {v['detail']}")
            elif v['score'] < 0.50:
                gaps.append(f"Weak {label}: {v['score']*100:.0f}% — {v['detail']}")

        # Missing skills
        req_lower  = [r.lower() for r in job_data['req_skills']]
        cand_lower = [c.lower() for c in candidate_data['skills']]
        missing    = [r for r in req_lower if not any(r in c or c in r for c in cand_lower)]
        if missing:
            gaps.insert(0, f"Missing skills: {', '.join(missing)}")

        if decision == 'shortlist':
            reco = (
                f"{student.name} is a strong candidate for the {job.title} role "
                f"(fit score {weighted_score*100:.1f}%). "
                "Recommend advancing to the interview stage."
            )
        elif decision == 'review':
            reco = (
                f"{student.name} shows moderate fit ({weighted_score*100:.1f}%) for {job.title}. "
                f"Manual review advised. Key concerns: {'; '.join(gaps[:2]) or 'see gaps below'}."
            )
        else:
            reco = (
                f"{student.name} does not meet minimum requirements ({weighted_score*100:.1f}%) for {job.title}. "
                f"Key gaps: {'; '.join(gaps[:2]) or 'overall low scores across dimensions'}."
            )

        self._log(
            6,
            '📊 Generate Fit Report',
            "Compiling strengths, gaps, and written recommendation…",
            f"Strengths found: {len(strengths)} | Gaps identified: {len(gaps)} | Recommendation written",
            {'strengths': strengths, 'gaps': gaps}
        )
        return {
            'overall_score':      weighted_score,
            'decision':           decision,
            'confidence':         '',           # filled in run()
            'strengths':          strengths or ['No outstanding strengths detected from available data'],
            'gaps':               gaps or ['No critical gaps identified'],
            'recommendation':     reco,
            'feature_breakdown':  breakdown,
        }

    # ── step 7: apply decision to application ─────────────────────────────────

    def _step7_apply_decision(self, application, decision):
        old_status = application.status
        new_status = old_status

        if decision == 'shortlist' and application.status == 'applied':
            application.status = 'shortlisted'
            application.save()
            new_status = 'shortlisted'
        elif decision == 'reject' and application.status == 'applied':
            application.status = 'rejected'
            application.save()
            new_status = 'rejected'
        # 'review' → leave status as-is for human to decide

        changed = old_status != new_status
        self._log(
            7,
            '✅ Apply Decision to Application',
            f"Writing decision back to the application record…",
            (
                f"Status: {old_status} → {new_status}"
                + (" ✓ updated" if changed else " (no change — requires manual action)")
            ),
            {'old_status': old_status, 'new_status': new_status, 'changed': changed}
        )

    # ── public entry point ────────────────────────────────────────────────────

    def run(self, application, triggered_by='auto'):
        """
        Execute all 7 steps, persist results, and return the RecruitmentAgentRun record.
        Safe to call from both auto-trigger (post-apply) and manual re-run.
        """
        from core.models import RecruitmentAgentRun

        self.steps = []

        run = RecruitmentAgentRun.objects.create(
            application=application,
            triggered_by=triggered_by,
            status='running',
        )

        try:
            student = application.student
            job     = application.job

            candidate_data = self._step1_gather_candidate(student)
            job_data       = self._step2_analyse_job(job)
            feature_scores = self._step3_compute_scores(candidate_data, job_data)
            weighted_score, breakdown, weights = self._step4_apply_weights(feature_scores, job=job)
            decision, confidence = self._step5_decide(weighted_score)
            fit_report = self._step6_fit_report(
                student, job, feature_scores, weighted_score,
                decision, breakdown, candidate_data, job_data
            )
            fit_report['confidence'] = confidence
            self._step7_apply_decision(application, decision)

            run.status          = 'completed'
            run.score           = weighted_score
            run.decision        = decision
            run.confidence      = confidence
            run.reasoning_steps = self.steps
            run.fit_report      = fit_report
            run.weights_used    = weights
            run.save()

        except Exception as e:
            self.steps.append({
                'step':      'ERROR',
                'action':    '❌ Agent Failed',
                'thought':   'An unexpected exception stopped the agent',
                'result':    str(e),
                'data':      {'traceback': traceback.format_exc()},
                'timestamp': datetime.now().strftime('%H:%M:%S'),
            })
            run.status          = 'failed'
            run.reasoning_steps = self.steps
            run.save()

        return run
