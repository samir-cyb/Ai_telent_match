from datetime import datetime, timedelta
from django.db.models import Avg, Count
from core.models import FraudFlag, Student, StudentSkill, Application

class FraudDetectionEngine:
    """Rule-based fraud detection for student profiles"""
    
    def __init__(self):
        self.flags = []
    
    def analyze_student(self, student):
        """Run all fraud detection rules on a student"""
        self.flags = []
        
        # Rule 1: CGPA-Project Mismatch
        self._check_cgpa_project_mismatch(student)
        
        # Rule 2: Skill Inflation
        self._check_skill_inflation(student)
        
        # Rule 3: GitHub Inconsistency
        self._check_github_consistency(student)
        
        # Rule 4: Rapid Profile Changes
        self._check_rapid_changes(student)
        
        # Rule 5: Impossible Experience Timeline
        self._check_experience_timeline(student)
        
        # Rule 6: Suspicious Application Pattern
        self._check_application_pattern(student)
        
        # Rule 7: CGPA Inflation Over Time
        self._check_cgpa_inflation(student)
        
        # Save flags
        for flag in self.flags:
            FraudFlag.objects.get_or_create(
                student=student,
                flag_type=flag['type'],
                defaults={
                    'severity': flag['severity'],
                    'details': flag['details'],
                    'resolved': False
                }
            )
        
        return self.flags
    
    def _check_cgpa_project_mismatch(self, student):
        """Flag: High CGPA but zero projects"""
        if student.cgpa and student.cgpa >= 3.8:
            project_count = student.projects.count()
            if project_count == 0:
                self.flags.append({
                    'type': 'cgpa_project_mismatch',
                    'severity': 'medium',
                    'details': {
                        'cgpa': float(student.cgpa),
                        'project_count': 0,
                        'reason': 'High CGPA (>=3.8) with no projects indicates possible grade inflation or incomplete profile'
                    }
                })
    
    def _check_skill_inflation(self, student):
        """Flag: More expert-level skills than plausible"""
        expert_skills = StudentSkill.objects.filter(
            student=student,
            proficiency_level='Expert'
        ).count()
        
        total_skills = StudentSkill.objects.filter(student=student).count()
        
        if total_skills > 0:
            expert_ratio = expert_skills / total_skills
            # If claiming expert in >70% of skills with <3 projects
            if expert_ratio > 0.7 and student.projects.count() < 3:
                self.flags.append({
                    'type': 'skill_inflation',
                    'severity': 'high',
                    'details': {
                        'expert_skills': expert_skills,
                        'total_skills': total_skills,
                        'projects': student.projects.count(),
                        'reason': 'Claiming expert level in most skills without sufficient project evidence'
                    }
                })
    
    def _check_github_consistency(self, student):
        """Flag: GitHub username doesn't match claimed projects"""
        if student.github_username and student.github_verified:
            from core.utils.github_scraper import GitHubValidator
            validator = GitHubValidator()
            
            # Check all GitHub URLs in projects
            for project in student.projects.all():
                if project.github_url and 'github.com' in project.github_url:
                    is_valid = validator.verify_project_link(
                        student.github_username, 
                        project.github_url
                    )
                    if not is_valid:
                        self.flags.append({
                            'type': 'github_mismatch',
                            'severity': 'high',
                            'details': {
                                'claimed_username': student.github_username,
                                'project_url': project.github_url,
                                'reason': 'Project URL does not belong to claimed GitHub account'
                            }
                        })
    
    def _check_rapid_changes(self, student):
        """Flag: Suspicious profile update patterns"""
        # Check if CGPA changed multiple times recently
        recent_updates = FraudFlag.objects.filter(
            student=student,
            flag_type='cgpa_changed',
            created_at__gte=datetime.now() - timedelta(days=7)
        ).count()
        
        if recent_updates > 3:
            self.flags.append({
                'type': 'rapid_profile_changes',
                'severity': 'low',
                'details': {
                    'recent_changes': recent_updates,
                    'reason': 'Multiple profile updates in short timeframe may indicate gaming the system'
                }
            })
    
    def _check_experience_timeline(self, student):
        """Flag: Overlapping work experiences"""
        experiences = list(student.experiences.all())
        
        for i, exp1 in enumerate(experiences):
            for exp2 in experiences[i+1:]:
                # Check for overlap
                if (exp1.start_date and exp1.end_date and 
                    exp2.start_date and exp2.end_date):
                    
                    # Overlap detection
                    if (exp1.start_date <= exp2.end_date and 
                        exp2.start_date <= exp1.end_date):
                        
                        # Allow if one is current (part-time possible)
                        if not (exp1.is_current or exp2.is_current):
                            self.flags.append({
                                'type': 'impossible_timeline',
                                'severity': 'medium',
                                'details': {
                                    'company1': exp1.company_name,
                                    'company2': exp2.company_name,
                                    'overlap_period': f"{max(exp1.start_date, exp2.start_date)} to {min(exp1.end_date, exp2.end_date)}",
                                    'reason': 'Overlapping full-time employment periods detected'
                                }
                            })
    
    def _check_application_pattern(self, student):
        """Flag: Suspicious application patterns"""
        # Check for mass applications in short time
        recent_apps = Application.objects.filter(
            student=student,
            applied_at__gte=datetime.now() - timedelta(hours=1)
        ).count()
        
        if recent_apps > 20:
            self.flags.append({
                'type': 'mass_application',
                'severity': 'low',
                'details': {
                    'recent_applications': recent_apps,
                    'reason': 'Unusually high number of applications in short timeframe'
                }
            })
        
        # Check for applications with very low match scores
        low_match_apps = Application.objects.filter(
            student=student,
            match_score__lt=30
        ).count()
        
        total_apps = Application.objects.filter(student=student).count()
        
        if total_apps > 0 and (low_match_apps / total_apps) > 0.8:
            self.flags.append({
                'type': 'low_match_spam',
                'severity': 'medium',
                'details': {
                    'low_match_count': low_match_apps,
                    'total_applications': total_apps,
                    'reason': 'Most applications have very low match scores - possible spam behavior'
                }
            })
    
    def _check_cgpa_inflation(self, student):
        """Flag: CGPA increased suspiciously fast"""
        # Check for recent CGPA changes in fraud flags
        recent_cgpa_flags = FraudFlag.objects.filter(
            student=student,
            flag_type='cgpa_changed',
            created_at__gte=datetime.now() - timedelta(days=30)
        ).order_by('-created_at')
        
        if recent_cgpa_flags.count() >= 2:
            self.flags.append({
                'type': 'cgpa_inflation_pattern',
                'severity': 'medium',
                'details': {
                    'recent_changes': recent_cgpa_flags.count(),
                    'reason': 'Multiple CGPA updates in 30 days - possible grade manipulation'
                }
            })
    
    def batch_analyze(self, students=None):
        """Run fraud detection on multiple students"""
        if students is None:
            # Analyze students updated in last 24 hours
            students = Student.objects.filter(
                updated_at__gte=datetime.now() - timedelta(days=1)
            )
        
        results = []
        for student in students:
            flags = self.analyze_student(student)
            if flags:
                results.append({
                    'student_id': str(student.id),
                    'student_name': student.name,
                    'flags_count': len(flags),
                    'severity': max((f['severity'] for f in flags), key=lambda x: {'low': 1, 'medium': 2, 'high': 3}.get(x, 0))
                })
        
        return results
    
    def get_fraud_statistics(self):
        """Get platform-wide fraud detection statistics"""
        total_flags = FraudFlag.objects.filter(resolved=False).count()
        
        by_severity = {
            'high': FraudFlag.objects.filter(severity='high', resolved=False).count(),
            'medium': FraudFlag.objects.filter(severity='medium', resolved=False).count(),
            'low': FraudFlag.objects.filter(severity='low', resolved=False).count()
        }
        
        by_type = {}
        for flag_type in FraudFlag.objects.values_list('flag_type', flat=True).distinct():
            by_type[flag_type] = FraudFlag.objects.filter(
                flag_type=flag_type, 
                resolved=False
            ).count()
        
        # Trend over last 7 days
        recent_trend = []
        for i in range(7):
            date = datetime.now().date() - timedelta(days=i)
            count = FraudFlag.objects.filter(
                created_at__date=date
            ).count()
            recent_trend.append({
                'date': date.isoformat(),
                'count': count
            })
        
        return {
            'total_flags': total_flags,
            'by_severity': by_severity,
            'by_type': by_type,
            'recent_trend': recent_trend
        }