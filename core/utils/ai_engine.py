import numpy as np
from datetime import datetime, timedelta
from django.db.models import Avg, Count
from core.models import AIFeedbackLog, Application, Job, Student, StudentSkill, MatchExplanation, Skill, StudentBehaviorLog
from django.utils import timezone


# Default matching weights per department category.
# Company custom_weights always override these via merge (see __init__).
DEPARTMENT_DEFAULT_WEIGHTS = {
    'tech': {
        'skills': 0.40, 'cgpa': 0.15, 'projects': 0.25,
        'activity': 0.10, 'trust': 0.10,
    },
    'engineering': {
        'skills': 0.35, 'cgpa': 0.25, 'projects': 0.25,
        'activity': 0.05, 'trust': 0.10,
    },
    'business': {
        'skills': 0.25, 'cgpa': 0.25, 'projects': 0.10,
        'activity': 0.25, 'trust': 0.15,
    },
    'design': {
        'skills': 0.20, 'cgpa': 0.10, 'projects': 0.45,
        'activity': 0.15, 'trust': 0.10,
    },
    'science': {
        'skills': 0.30, 'cgpa': 0.35, 'projects': 0.20,
        'activity': 0.05, 'trust': 0.10,
    },
    'humanities': {
        'skills': 0.20, 'cgpa': 0.25, 'projects': 0.10,
        'activity': 0.30, 'trust': 0.15,
    },
    'any': {
        'skills': 0.35, 'cgpa': 0.20, 'projects': 0.20,
        'activity': 0.15, 'trust': 0.10,
    },
}


class AIMatchingEngine:
    def __init__(self, company=None, job=None):
        self.company = company
        self.job = job

        # 1. Start from department-based defaults (from the job, if available)
        dept_cat = getattr(job, 'department_category', 'any') or 'any'
        base_weights = DEPARTMENT_DEFAULT_WEIGHTS.get(dept_cat, DEPARTMENT_DEFAULT_WEIGHTS['any']).copy()

        # 2. Company custom_weights override department defaults
        if company and company.custom_weights:
            base_weights = {**base_weights, **company.custom_weights}

        # 3. Job-level custom_weights have the highest priority
        if job and job.custom_weights:
            base_weights = {**base_weights, **job.custom_weights}

        self.weights = base_weights
        self.department_category = dept_cat

        # A/B Testing
        self.ab_test_variant = None
    
    def get_ab_test_weights(self, student):
        """Apply A/B testing variant weights if applicable"""
        if not student.ab_test_group or student.ab_test_group == 'control':
            return self.weights
        
        # Variant A: Enhanced weighting with more emphasis on projects and verified skills
        if student.ab_test_group == 'variant_a':
            return {
                'skills': 0.35,
                'cgpa': 0.15,
                'projects': 0.30,  # Increased project weight
                'activity': 0.10,
                'trust': 0.10
            }
        
        # Variant B: Activity-focused weighting
        if student.ab_test_group == 'variant_b':
            return {
                'skills': 0.30,
                'cgpa': 0.15,
                'projects': 0.20,
                'activity': 0.25,  # Increased activity weight
                'trust': 0.10
            }
        
        return self.weights
    
    # Semantic skill similarity groups.
    # If a student has skill A and job requires skill B (a related skill),
    # they receive PARTIAL_SEMANTIC_SCORE credit instead of zero.
    SKILL_SIMILARITY_GROUPS = {
        # Frontend frameworks
        'react': ['vue', 'angular', 'svelte', 'next.js', 'nuxt'],
        'vue': ['react', 'angular', 'svelte'],
        'angular': ['react', 'vue', 'svelte'],
        # Backend frameworks
        'django': ['flask', 'fastapi', 'rails', 'laravel', 'express'],
        'flask': ['django', 'fastapi', 'express'],
        'fastapi': ['django', 'flask', 'express'],
        'express': ['django', 'flask', 'fastapi', 'spring boot'],
        # Languages (similar paradigm)
        'python': ['r', 'julia', 'matlab'],
        'javascript': ['typescript'],
        'typescript': ['javascript'],
        'java': ['kotlin', 'scala', 'c#'],
        'c#': ['java', 'kotlin'],
        'kotlin': ['java', 'swift'],
        'swift': ['kotlin', 'objective-c'],
        # Data / ML
        'tensorflow': ['pytorch', 'keras'],
        'pytorch': ['tensorflow', 'keras'],
        'pandas': ['numpy', 'polars'],
        'scikit-learn': ['xgboost', 'lightgbm'],
        # Databases
        'postgresql': ['mysql', 'mariadb', 'sqlite'],
        'mysql': ['postgresql', 'mariadb', 'sqlite'],
        'mongodb': ['couchdb', 'dynamodb', 'firestore'],
        # Cloud
        'aws': ['gcp', 'azure'],
        'gcp': ['aws', 'azure'],
        'azure': ['aws', 'gcp'],
        # Design
        'figma': ['sketch', 'adobe xd', 'invision'],
        'adobe photoshop': ['gimp', 'affinity photo'],
        # Business
        'excel': ['google sheets', 'tableau', 'power bi'],
        'tableau': ['power bi', 'looker', 'excel'],
    }
    PARTIAL_SEMANTIC_SCORE = 0.4  # credit for a semantically similar skill

    def calculate_skill_match(self, student, job):
        """
        Semantic skill matching with cross-validation boost.

        Scoring per required skill:
          - Exact match + cross_validated:  proficiency_multiplier × 1.2  (capped 1.0)
          - Exact match (not cross-validated): proficiency_multiplier (0.5/0.8/1.0)
          - Semantic similar skill found:   PARTIAL_SEMANTIC_SCORE (0.4)
          - Not found at all:               0 (added to missing list)
        """
        required_skills = list(job.required_skills.all())
        student_skills_qs = StudentSkill.objects.filter(student=student).select_related('skill')

        # Build lookup: lowercase name → {level, cross_validated}
        student_skills_by_name = {}
        for ss in student_skills_qs:
            student_skills_by_name[ss.skill.name.lower()] = {
                'level': ss.proficiency_level,
                'cross_validated': getattr(ss, 'cross_validated', False),
            }

        if not required_skills:
            return 1.0, []

        matched = 0.0
        missing = []

        prof_map = {'Beginner': 0.5, 'Intermediate': 0.8, 'Expert': 1.0}

        for required_skill in required_skills:
            req_lower = required_skill.name.lower()

            if req_lower in student_skills_by_name:
                # Exact match
                entry = student_skills_by_name[req_lower]
                multiplier = prof_map.get(entry['level'], 0.5)
                if entry['cross_validated']:
                    multiplier = min(multiplier * 1.2, 1.0)  # CV+LinkedIn verified → boost
                matched += multiplier
            else:
                # Try semantic partial match
                similar_names = self.SKILL_SIMILARITY_GROUPS.get(req_lower, [])
                found_similar = False
                for sim_name in similar_names:
                    if sim_name in student_skills_by_name:
                        matched += self.PARTIAL_SEMANTIC_SCORE
                        found_similar = True
                        break
                if not found_similar:
                    missing.append(required_skill)

        return matched / len(required_skills), missing
    
    def calculate_cgpa_score(self, student, job):
        """Normalize CGPA to 0-1 scale"""
        if not student.cgpa or not job.min_cgpa:
            return 1.0 if not job.min_cgpa else 0.0
        
        if student.cgpa < job.min_cgpa:
            return 0.0
        
        return min(float(student.cgpa) / 4.0, 1.0)
    
    def calculate_project_score(self, student):
        """Score based on project complexity and relevance"""
        projects = student.projects.all()
        if not projects:
            return 0.0
        
        total_score = 0
        for proj in projects:
            complexity = proj.complexity_score
            verified_bonus = 1.2 if proj.verified else 1.0
            total_score += (complexity * verified_bonus)
        
        return min(total_score / 25.0, 1.0)
    
    def calculate_activity_score(self, student):
        """Normalize activity score"""
        if not student.activity_score:
            return 0.0
        return min(float(student.activity_score) / 100.0, 1.0)
    
    def calculate_contextual_factors(self, student, job):
        """Additional contextual adjustments"""
        factors = {
            'availability_penalty': 0,
            'competition_factor': 1.0,
            'reapplication_penalty': 0
        }
        
        # Graduation timing
        if student.graduation_date:
            months_until_grad = (student.graduation_date - timezone.now().date()).days / 30
            if months_until_grad > 6:
                factors['availability_penalty'] = -0.1
        
        # Competition density
        applicant_count = Application.objects.filter(job=job).count()
        if applicant_count > 50:
            factors['competition_factor'] = 0.95
        if applicant_count > 100:
            factors['competition_factor'] = 0.9
        
        # Previous rejection (3-month cooldown)
        recent_rejection = Application.objects.filter(
            student=student,
            job__company=job.company,
            status='rejected',
            updated_at__gte=timezone.now() - timedelta(days=90)
        ).exists()
        
        if recent_rejection:
            factors['reapplication_penalty'] = -0.2
        
        # Intent signals from behavior logs
        viewed_count = StudentBehaviorLog.objects.filter(
            student=student,
            job=job,
            action='viewed'
        ).count()
        
        if viewed_count > 3:
            # Student is very interested
            factors['interest_bonus'] = 0.05
        
        return factors
    
    def generate_explanation(self, student, job, scores, missing_skills, factors):
        """Generate human-readable explanation for the match score"""
        recommendations = []
        
        # Skill gap advice
        if missing_skills:
            skill_names = [s.name for s in missing_skills]
            recommendations.append(f"To qualify for this role, you should learn: {', '.join(skill_names)}")
        
        # CGPA advice
        if scores['cgpa'] < 0.7 and job.min_cgpa:
            recommendations.append(f"Consider improving your CGPA (current: {student.cgpa}, required: {job.min_cgpa})")
        
        # Project advice
        if scores['projects'] < 0.5:
            recommendations.append("Build 2-3 more projects with higher complexity to improve your score")
        
        # Trust score advice
        if scores['trust'] < 0.6:
            recommendations.append("Complete your profile verification and take skill assessments to boost trust score")
        
        # A/B test info
        ab_test_info = None
        if student.ab_test_group and student.ab_test_group != 'control':
            ab_test_info = {
                'group': student.ab_test_group,
                'description': self._get_ab_test_description(student.ab_test_group)
            }
        
        # Radar chart data for visualization
        radar_data = {
            'labels': ['Skills', 'CGPA', 'Projects', 'Activity', 'Trust'],
            'student_scores': [
                scores['skills'] * 100,
                scores['cgpa'] * 100,
                scores['projects'] * 100,
                scores['activity'] * 100,
                scores['trust'] * 100
            ],
            'job_requirements': [
                80,  # Skills threshold
                float(job.min_cgpa or 3.0) / 4.0 * 100 if job.min_cgpa else 60,
                60,  # Project threshold
                40,  # Activity threshold
                50   # Trust threshold
            ]
        }
        
        return {
            'breakdown': scores,
            'recommendations': recommendations,
            'radar_chart': radar_data,
            'contextual_factors': factors,
            'missing_skills': [{'id': str(s.id), 'name': s.name} for s in missing_skills] if missing_skills else [],
            'ab_test_info': ab_test_info
        }
    
    def _get_ab_test_description(self, group):
        """Get description for A/B test group"""
        descriptions = {
            'variant_a': 'Enhanced project-weighted algorithm',
            'variant_b': 'Activity-focused algorithm'
        }
        return descriptions.get(group, 'Standard algorithm')
    
    def _linkedin_trust_bonus(self, student):
        """
        Compute LinkedIn trust bonus (0–0.20) using linkedin_score when available,
        falling back to flat URL bonus so existing profiles aren't penalised.
        """
        ls = getattr(student, 'linkedin_score', 0) or 0
        if ls > 0:
            # linkedin_score 0–100 → bonus 0–0.20 (proportional, richer profile = higher trust)
            return (ls / 100.0) * 0.20
        # Fallback: just having the URL gives a small flat bonus
        return 0.07 if student.linkedin_url else 0.0

    def calculate_trust_score_dept_aware(self, student):
        """
        Build a 0–1 trust score that accounts for the student's department.
        LinkedIn score (from PDF verification) is now the primary LinkedIn signal,
        replacing the old flat URL check. Cross-validated skills add a small bonus.
        """
        dept_cat = (
            getattr(student, 'department_category', None)
            or student.get_department_category()
        )

        # Base: profile trust score (always relevant)
        base = float(student.trust_score) / 100.0 if student.trust_score else 0.0

        # Cross-validation bonus: each verified skill adds a tiny trust signal
        cv_count = StudentSkill.objects.filter(student=student, cross_validated=True).count()
        cross_val_bonus = min(cv_count * 0.01, 0.05)  # max +5% from cross-validated skills
        base = min(base + cross_val_bonus, 1.0)

        if dept_cat == 'tech':
            # GitHub score → up to +20% | LinkedIn PDF score → up to +10% for tech
            github_bonus = (float(student.github_score) / 100.0) * 0.2 if student.github_score else 0.0
            linkedin_bonus = self._linkedin_trust_bonus(student) * 0.5  # half weight for tech
            return min(base + github_bonus + linkedin_bonus, 1.0)

        if dept_cat == 'design':
            # Behance/portfolio → +10% | LinkedIn PDF → up to +10%
            portfolio_bonus = 0.10 if (getattr(student, 'behance_url', '') or student.portfolio_url) else 0.0
            linkedin_bonus = self._linkedin_trust_bonus(student) * 0.5
            return min(base + portfolio_bonus + linkedin_bonus, 1.0)

        if dept_cat in ('business', 'humanities'):
            # LinkedIn is the PRIMARY signal here → full weight (up to +20%)
            linkedin_bonus = self._linkedin_trust_bonus(student)
            eca_bonus = min(len(getattr(student, 'eca_activities', []) or []) * 0.02, 0.08)
            return min(base + linkedin_bonus + eca_bonus, 1.0)

        if dept_cat == 'science':
            # Research papers → up to +15% | LinkedIn PDF → up to +10%
            paper_bonus = min(len(getattr(student, 'research_papers', []) or []) * 0.05, 0.15)
            linkedin_bonus = self._linkedin_trust_bonus(student) * 0.5
            return min(base + paper_bonus + linkedin_bonus, 1.0)

        # engineering / any: LinkedIn PDF at full weight
        linkedin_bonus = self._linkedin_trust_bonus(student)
        return min(base + linkedin_bonus, 1.0)

    def calculate_match(self, student, job, save_explanation=True):
        """Main matching algorithm with A/B testing and department-aware support"""
        # Get appropriate weights based on A/B test group
        weights = self.get_ab_test_weights(student)

        # Base scores
        skill_score, missing_skills = self.calculate_skill_match(student, job)
        cgpa_score = self.calculate_cgpa_score(student, job)
        project_score = self.calculate_project_score(student)
        activity_score = self.calculate_activity_score(student)
        trust_score = self.calculate_trust_score_dept_aware(student)
        
        # Contextual adjustments
        factors = self.calculate_contextual_factors(student, job)
        
        # Weighted calculation
        base_score = (
            skill_score * weights['skills'] +
            cgpa_score * weights['cgpa'] +
            project_score * weights['projects'] +
            activity_score * weights['activity'] +
            trust_score * weights['trust']
        )
        
        # Apply contextual adjustments
        adjusted_score = base_score * factors.get('competition_factor', 1.0)
        adjusted_score += factors.get('availability_penalty', 0)
        adjusted_score += factors.get('reapplication_penalty', 0)
        adjusted_score += factors.get('interest_bonus', 0)
        
        # Clamp to 0-100
        final_score = max(0, min(100, adjusted_score * 100))
        
        scores = {
            'skills': skill_score,
            'cgpa': cgpa_score,
            'projects': project_score,
            'activity': activity_score,
            'trust': trust_score,
            'final': final_score,
            'weights_used': weights  # Include weights for transparency
        }
        
        explanation_data = self.generate_explanation(student, job, scores, missing_skills, factors)
        
        return final_score, explanation_data
    
    def generate_smart_recommendations(self, student, top_n=5):
        """
        Return top N jobs ranked by match score, each with:
          - fit_percentage: current match %
          - gap_skills: list of skills the student is missing
          - potential_score: estimated score if gap skills were added
          - is_reachable: True if potential_score >= 70 (worth pursuing)

        Also returns career_guide: the most impactful skills to add across
        all near-miss jobs (60–85% fit range).
        """
        active_jobs = Job.objects.filter(status='active').prefetch_related('required_skills', 'company')
        results = []

        for job in active_jobs:
            engine = AIMatchingEngine(company=job.company, job=job)
            score, explanation = engine.calculate_match(student, job, save_explanation=False)
            missing = explanation.get('missing_skills', [])

            # Estimate potential score: assume adding each missing skill at Intermediate
            # gives the average contribution of that skill to the total weight
            skills_weight = engine.weights.get('skills', 0.35)
            req_count = job.required_skills.count()
            if req_count > 0 and missing:
                # Each missing skill contributes skills_weight * 0.8 / req_count (Intermediate)
                gain_per_skill = (skills_weight * 0.8 / req_count) * 100
                potential = min(score + gain_per_skill * len(missing), 100)
            else:
                potential = score

            results.append({
                'job_id': str(job.id),
                'job_title': job.title,
                'company_name': job.company.name,
                'fit_percentage': round(score, 1),
                'potential_score': round(potential, 1),
                'gap_skills': missing,
                'is_reachable': potential >= 70,
                'department_category': job.department_category or 'any',
            })

        # Sort: prioritise reachable jobs closest to 80% fit
        results.sort(key=lambda x: (
            -x['is_reachable'],
            -x['fit_percentage'],
        ))
        top_jobs = results[:top_n]

        # Career guide: find the most commonly missing skills across 60–85% fit jobs
        near_miss_jobs = [r for r in results if 55 <= r['fit_percentage'] <= 85]
        skill_frequency: dict = {}
        for r in near_miss_jobs:
            for s in r['gap_skills']:
                key = s['name']
                skill_frequency[key] = skill_frequency.get(key, 0) + 1

        # Top 5 highest-impact skills to learn
        top_gap_skills = sorted(skill_frequency.items(), key=lambda x: -x[1])[:5]
        career_guide = []
        for skill_name, job_count in top_gap_skills:
            career_guide.append({
                'skill': skill_name,
                'unlocks_jobs': job_count,
                'message': f"Adding '{skill_name}' would improve your fit for {job_count} job{'s' if job_count > 1 else ''}",
            })

        return {
            'top_jobs': top_jobs,
            'career_guide': career_guide,
            'total_active_jobs': len(results),
        }

    def smart_apply(self, student, threshold=70, max_applications=5):
        """Auto-apply student to best matching jobs"""
        active_jobs = Job.objects.filter(status='active')
        matches = []
        
        for job in active_jobs:
            # Skip if already applied
            if Application.objects.filter(student=student, job=job).exists():
                continue
            
            score, explanation = self.calculate_match(student, job, save_explanation=False)
            
            if score >= threshold:
                matches.append({
                    'job': job,
                    'score': score,
                    'explanation': explanation
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        # Auto-apply to top N
        applied = []
        for match in matches[:max_applications]:
            app = Application.objects.create(
                student=student,
                job=match['job'],
                match_score=match['score'],
                is_auto_applied=True,
                status='applied'
            )
            
            # Save explanation
            MatchExplanation.objects.create(
                application=app,
                score_breakdown=match['explanation']['breakdown'],
                recommendations=match['explanation']['recommendations'],
                radar_chart_data=match['explanation']['radar_chart']
            )
            
            # Add skill gaps
            for skill_data in match['explanation']['missing_skills']:
                skill = Skill.objects.get(id=skill_data['id'])
                app.explanation.skill_gaps.add(skill)
            
            applied.append({
                'application_id': str(app.id),
                'job_title': match['job'].title,
                'company': match['job'].company.name,
                'score': match['score']
            })
        
        return applied
    
    def update_weights_from_feedback(self, company, hired_application):
        """Reinforcement learning: adjust weights based on successful hire"""
        student = hired_application.student
        job = hired_application.job
        
        # Get the hired student's profile vector
        successful_vector = {
            'skills': self.calculate_skill_match(student, job)[0],
            'cgpa': self.calculate_cgpa_score(student, job),
            'projects': self.calculate_project_score(student),
            'activity': self.calculate_activity_score(student),
            'trust': student.trust_score / 100.0 if student.trust_score else 0.0
        }
        
        # Current weights
        current_weights = company.get_weights()
        
        # Learning rate (small adjustments)
        learning_rate = 0.05
        
        # Shift weights toward successful features
        total = sum(successful_vector.values())
        if total > 0:
            ideal_weights = {k: v/total for k, v in successful_vector.items()}
            
            new_weights = {}
            for key in current_weights:
                # Move 5% toward ideal
                new_weights[key] = current_weights[key] + learning_rate * (ideal_weights[key] - current_weights[key])
            
            # Normalize to ensure sum = 1
            weight_sum = sum(new_weights.values())
            new_weights = {k: v/weight_sum for k, v in new_weights.items()}
            
            # Save to company
            company.custom_weights = new_weights
            company.successful_hire_patterns.append({
                'date': datetime.now().isoformat(),
                'student_id': str(student.id),
                'job_id': str(job.id),
                'profile_vector': successful_vector
            })
            company.save()
            
            # Log the adjustment
            AIFeedbackLog.objects.create(
                company=company,
                application=hired_application,
                previous_weights=current_weights,
                adjusted_weights=new_weights,
                adjustment_reason=f"Successful hire of {student.name} for {job.title}"
            )
            
            return new_weights
        
        return current_weights


class ABTestFramework:
    """A/B Testing framework for matching algorithms"""
    
    VARIANTS = ['control', 'variant_a', 'variant_b']
    
    @staticmethod
    def assign_variant(student):
        """Randomly assign student to A/B test variant"""
        import random
        variant = random.choice(ABTestFramework.VARIANTS)
        student.ab_test_group = variant
        student.save()
        return variant
    
    @staticmethod
    def calculate_variant_performance():
        """Calculate performance metrics for each variant"""
        results = {}
        
        for variant in ABTestFramework.VARIANTS:
            apps = Application.objects.filter(student__ab_test_group=variant)
            
            total = apps.count()
            hired = apps.filter(status='hired').count()
            shortlisted = apps.filter(status='shortlisted').count()
            interviews = apps.filter(status='interview').count()
            
            # Calculate conversion rates
            hire_rate = (hired / total * 100) if total > 0 else 0
            shortlist_rate = (shortlisted / total * 100) if total > 0 else 0
            interview_rate = (interviews / total * 100) if total > 0 else 0
            
            # Average match scores
            avg_score = apps.aggregate(Avg('match_score'))['match_score__avg'] or 0
            
            results[variant] = {
                'total': total,
                'hired': hired,
                'shortlisted': shortlisted,
                'interviews': interviews,
                'hire_rate': round(hire_rate, 2),
                'shortlist_rate': round(shortlist_rate, 2),
                'interview_rate': round(interview_rate, 2),
                'avg_match_score': round(avg_score, 2)
            }
        
        return results
    
    @staticmethod
    def get_statistical_significance():
        """Calculate statistical significance between variants"""
        # Simplified - in production use proper statistical tests
        performance = ABTestFramework.calculate_variant_performance()
        
        control_rate = performance['control']['hire_rate']
        variant_a_rate = performance['variant_a']['hire_rate']
        variant_b_rate = performance['variant_b']['hire_rate']
        
        def calculate_improvement(variant_rate):
            if control_rate == 0:
                return 0
            return round(((variant_rate - control_rate) / control_rate) * 100, 1)
        
        return {
            'control': performance['control'],
            'variant_a': {
                **performance['variant_a'],
                'improvement': calculate_improvement(variant_a_rate),
                'significant': abs(variant_a_rate - control_rate) > 5  # 5% threshold
            },
            'variant_b': {
                **performance['variant_b'],
                'improvement': calculate_improvement(variant_b_rate),
                'significant': abs(variant_b_rate - control_rate) > 5
            }
        }