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
        skills   = list(StudentSkill.objects.filter(student=student).select_related('skill'))
        skill_names = [ss.skill.name for ss in skills]
        projects = list(student.projects.all())
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
                'project_count':  len(projects),
                'linkedin_score': student.linkedin_score,
                'github_score':   student.github_score,
                'trust_score':    float(student.trust_score or 0),
                'activity_score': float(student.activity_score or 0),
            }
        )
        return {
            'skills':         skill_names,
            'cgpa':           cgpa,
            'project_count':  len(projects),
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
        # Skills
        req  = [s.lower() for s in job_data['req_skills']]
        cand = [s.lower() for s in candidate_data['skills']]
        if req:
            matched      = sum(1 for r in req if any(r in c or c in r for c in cand))
            skills_score = matched / len(req)
            skills_detail = f"{matched}/{len(req)} required skills matched"
        else:
            skills_score  = 0.70
            skills_detail = "No skill requirements — defaulting to 70%"

        # CGPA
        cgpa     = candidate_data['cgpa']
        min_cgpa = job_data['min_cgpa']
        if cgpa > 0:
            cgpa_score = min(cgpa / 4.0, 1.0)
            if min_cgpa and cgpa < min_cgpa:
                cgpa_score  *= 0.5
                cgpa_detail  = f"CGPA {cgpa:.2f} below minimum {min_cgpa:.2f} — 50% penalty"
            else:
                cgpa_detail  = f"CGPA {cgpa:.2f}/4.0{' (meets minimum)' if min_cgpa else ''}"
        else:
            cgpa_score  = 0.50
            cgpa_detail = "CGPA not set — defaulting to 50%"

        # Projects
        pc             = candidate_data['project_count']
        projects_score = min(pc / 5.0, 1.0)
        projects_detail = f"{pc} project{'s' if pc != 1 else ''} (5 projects = 100%)"

        # Activity  (GitHub 60% + platform activity 40%)
        github_norm    = min(candidate_data['github_score'] / 100, 1.0)
        activity_raw   = candidate_data['activity_score']
        activity_score = round(github_norm * 0.6 + min(activity_raw / 100, 1.0) * 0.4, 3)
        activity_detail = f"GitHub: {candidate_data['github_score']} pts | Activity: {activity_raw:.0f}/100"

        # Trust  (LinkedIn 50% + profile trust 50%)
        linkedin_norm = candidate_data['linkedin_score'] / 100
        trust_raw     = candidate_data['trust_score']
        trust_score   = round(linkedin_norm * 0.5 + min(trust_raw / 100, 1.0) * 0.5, 3)
        trust_detail   = f"LinkedIn: {candidate_data['linkedin_score']}/100 | Trust: {trust_raw:.0f}/100"

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
            "Scoring across 5 dimensions: skills, CGPA, projects, activity, trust…",
            " | ".join(f"{k}: {v['score']*100:.0f}%" for k, v in scores.items()),
            {'scores': scores}
        )
        return scores

    # ── step 4: apply weights ─────────────────────────────────────────────────

    def _step4_apply_weights(self, feature_scores):
        weights  = self.company.get_weights()
        weighted = 0.0
        breakdown = {}

        for key, w in weights.items():
            fs     = feature_scores.get(key, {}).get('score', 0)
            contrib = round(fs * w, 4)
            breakdown[key] = {
                'score':        feature_scores.get(key, {}).get('score', 0),
                'weight':       round(w, 4),
                'contribution': contrib,
                'detail':       feature_scores.get(key, {}).get('detail', ''),
            }
            weighted += contrib

        weighted = round(weighted, 4)
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
            weighted_score, breakdown, weights = self._step4_apply_weights(feature_scores)
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
