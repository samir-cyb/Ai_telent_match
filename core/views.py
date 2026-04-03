import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Q, Avg, Count
from datetime import datetime, timedelta
from django.contrib.sessions.backends.db import SessionStore
from .decorators import student_login_required, company_login_required
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import *
from .utils.ai_engine import AIMatchingEngine
from .utils.github_scraper import GitHubValidator
from .utils.fraud_detector import FraudDetectionEngine

# ==================== PAGE RENDERING VIEWS ====================

def landing_page(request):
    return render(request, 'index.html')

def about_us(request):
    return render(request, 'about.html')

def services(request):
    return render(request, 'services.html')

def student_login(request):
    return render(request, 'auth/student_login.html')

def student_register(request):
    return render(request, 'auth/student_register.html')

def company_login(request):
    return render(request, 'auth/company_login.html')

def company_register(request):
    return render(request, 'auth/company_register.html')

@student_login_required
def student_dashboard(request):
    return render(request, 'student/dashboard.html')

@student_login_required
def student_profile(request):
    return render(request, 'student/profile.html')

@student_login_required
def student_job_detail(request):
    return render(request, 'student/job_detail.html')

@company_login_required
def company_dashboard(request):
    return render(request, 'company/dashboard.html')

@company_login_required
def company_post_job(request):
    return render(request, 'company/post_job.html')

@company_login_required
def company_applicants(request):
    return render(request, 'company/applicants.html')

def admin_dashboard(request):
    return render(request, 'admin/dashboard.html')

def admin_analytics(request):
    return render(request, 'admin/analytics.html')

def admin_fraud_review(request):
    return render(request, 'admin/fraud_review.html')

# ==================== AUTHENTICATION VIEWS ====================
@method_decorator(csrf_exempt, name='dispatch')
class StudentRegisterView(View):
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Check if email already exists
            if Student.objects.filter(email=data['email']).exists():
                return JsonResponse({'status': 'error', 'message': 'Email already registered'}, status=400)
            
            student = Student.objects.create(
                email=data['email'],
                university_id=data.get('university_id', ''),
                name=data['name'],
                department=data.get('department', ''),
                preferences={
                    'job_types': data.get('job_types', []),
                    'salary_expectation': data.get('salary_expectation', ''),
                    'company_size': data.get('company_size', []),
                    'willing_to_relocate': data.get('willing_to_relocate', False)
                }
            )
            student.set_password(data['password'])
            student.save()
            
            # Verify GitHub if provided
            if data.get('github_username'):
                validator = GitHubValidator()
                result = validator.validate_student_github(data['github_username'])
                if result['valid']:
                    student.github_verified = True
                    student.github_score = result['score']
                    student.save()
            
            # Calculate initial trust score
            student.calculate_trust_score()
            
            # Run fraud detection
            fraud_engine = FraudDetectionEngine()
            flags = fraud_engine.analyze_student(student)
            
            return JsonResponse({
                'status': 'success',
                'student_id': str(student.id),
                'trust_score': float(student.trust_score),
                'message': 'Registration successful'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
@method_decorator(csrf_exempt, name='dispatch')
class StudentLoginView(View):
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            student = Student.objects.filter(email=data['email']).first()
            
            if not student or not student.check_password(data['password']):
                return JsonResponse({'status': 'error', 'message': 'Invalid credentials'}, status=401)
            
            # Update activity
            student.last_login = datetime.now()
            student.login_frequency += 1
            student.save()
            
            # Create session
            request.session['student_id'] = str(student.id)
            request.session['user_type'] = 'student'
            
            return JsonResponse({
                'status': 'success',
                'student_id': str(student.id),
                'name': student.name,
                'redirect': '/student/dashboard/'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
@method_decorator(csrf_exempt, name='dispatch')
class CompanyRegisterView(View):
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            if Company.objects.filter(email=data['email']).exists():
                return JsonResponse({'status': 'error', 'message': 'Email already registered'}, status=400)
            
            company = Company.objects.create(
                email=data['email'],
                name=data['name'],
                industry=data.get('industry', ''),
                size=data.get('size', ''),
                website=data.get('website', ''),
                description=data.get('description', '')
            )
            company.set_password(data['password'])
            company.save()
            
            return JsonResponse({
                'status': 'success',
                'company_id': str(company.id),
                'message': 'Company registration successful'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class CompanyLoginView(View):
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            company = Company.objects.filter(email=data['email']).first()
            
            if not company or not company.check_password(data['password']):
                return JsonResponse({'status': 'error', 'message': 'Invalid credentials'}, status=401)
            
            request.session['company_id'] = str(company.id)
            request.session['user_type'] = 'company'
            
            return JsonResponse({
                'status': 'success',
                'company_id': str(company.id),
                'name': company.name,
                'redirect': '/company/dashboard/'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ==================== STUDENT VIEWS ====================
@method_decorator(csrf_exempt, name='dispatch') 
class StudentProfileView(View):
    @method_decorator(student_login_required)
    def get(self, request, student_id):
        student = get_object_or_404(Student, id=student_id)
        
        # Calculate current trust score
        student.calculate_trust_score()
        
        profile = {
            'id': str(student.id),
            'name': student.name,
            'email': student.email,
            'department': student.department,
            'cgpa': float(student.cgpa) if student.cgpa else None,
            'graduation_date': student.graduation_date.isoformat() if student.graduation_date else None,
            'preferences': student.preferences,
            'github': {
                'username': student.github_username,
                'verified': student.github_verified,
                'score': student.github_score
            },
            'trust_score': float(student.trust_score),
            'skills': [
                {
                    'name': ss.skill.name,
                    'category': ss.skill.category,
                    'level': ss.proficiency_level,
                    'verified': ss.verified_via
                } for ss in StudentSkill.objects.filter(student=student).select_related('skill')
            ],
            'projects': [
                {
                    'title': p.title,
                    'tech_stack': [s.name for s in p.tech_stack.all()],
                    'verified': p.verified,
                    'complexity': p.complexity_score
                } for p in student.projects.all()
            ],
            'experiences': [
                {
                    'company': e.company_name,
                    'role': e.role,
                    'duration': f"{e.start_date} to {e.end_date or 'Present'}",
                    'verified': e.verification_status
                } for e in student.experiences.all()
            ]
        }
        
        return JsonResponse({'status': 'success', 'data': profile})
    
    @method_decorator(csrf_exempt)
    def post(self, request):
        """Create or update student profile"""
        data = json.loads(request.body)
        
        student, created = Student.objects.update_or_create(
            email=data.get('email'),
            defaults={
                'university_id': data.get('university_id'),
                'name': data.get('name'),
                'department': data.get('department'),
                'cgpa': data.get('cgpa'),
                'graduation_date': data.get('graduation_date'),
                'preferences': data.get('preferences', {}),
                'github_username': data.get('github_username'),
                'linkedin_url': data.get('linkedin_url'),
                'portfolio_url': data.get('portfolio_url')
            }
        )
        
        # Verify GitHub if username provided
        if data.get('github_username'):
            validator = GitHubValidator()
            result = validator.validate_student_github(data['github_username'])
            if result['valid']:
                student.github_verified = True
                student.github_score = result['score']
                student.save()
        
        # Calculate initial trust score
        student.calculate_trust_score()
        
        # Run fraud detection
        fraud_engine = FraudDetectionEngine()
        flags = fraud_engine.analyze_student(student)
        
        return JsonResponse({
            'status': 'created' if created else 'updated',
            'student_id': str(student.id),
            'trust_score': float(student.trust_score),
            'fraud_flags': len(flags),
            'github_validation': result if data.get('github_username') else None
        })
@method_decorator(csrf_exempt, name='dispatch')
class AnalyzeMatchView(View):
    def post(self, request):
        """Analyze match between student and specific job"""
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=data['student_id'])
        job = get_object_or_404(Job, id=data['job_id'])
        
        # Get company weights
        engine = AIMatchingEngine(job.company)
        score, explanation = engine.calculate_match(student, job, save_explanation=False)
        
        # Log behavior (viewed analysis)
        StudentBehaviorLog.objects.create(
            student=student,
            job=job,
            action='viewed_analysis',
            duration_seconds=data.get('duration', 0)
        )
        
        return JsonResponse({
            'status': 'success',
            'match_score': score,
            'explanation': explanation
        })
@method_decorator(csrf_exempt, name='dispatch')
class SmartApplyView(View):
    
    def post(self, request):
        """Auto-apply to best matching jobs"""
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=data['student_id'])
        
        threshold = data.get('threshold', 70)
        max_applications = data.get('max_applications', 5)
        
        engine = AIMatchingEngine()
        applied = engine.smart_apply(student, threshold, max_applications)
        
        # Create notifications
        for app_data in applied:
            Notification.objects.create(
                user_id=student.id,
                user_type='student',
                type='auto_applied',
                title=f'Auto-applied to {app_data["job_title"]}',
                message=f'You were automatically applied to {app_data["job_title"]} at {app_data["company"]} with a match score of {app_data["score"]:.1f}%',
                data={'application_id': app_data['application_id']}
            )
        
        return JsonResponse({
            'status': 'success',
            'applied_count': len(applied),
            'applications': applied
        })

class StudentDashboardView(View):
    def get(self, request, student_id):
        """Rich analytics dashboard for student"""
        student = get_object_or_404(Student, id=student_id)
        
        # Get recommended jobs (score > 60, not applied)
        all_jobs = Job.objects.filter(status='active')
        recommendations = []
        
        for job in all_jobs:
            if not Application.objects.filter(student=student, job=job).exists():
                engine = AIMatchingEngine(job.company)
                score, explanation = engine.calculate_match(student, job, save_explanation=False)
                if score >= 60:
                    recommendations.append({
                        'job_id': str(job.id),
                        'title': job.title,
                        'company': job.company.name,
                        'match_score': score,
                        'skill_gaps': len(explanation['missing_skills']),
                        'salary': job.salary_range
                    })
        
        recommendations.sort(key=lambda x: x['match_score'], reverse=True)
        
        # Analytics
        total_applications = Application.objects.filter(student=student).count()
        shortlisted = Application.objects.filter(student=student, status='shortlisted').count()
        interviews = Application.objects.filter(student=student, status='interview').count()
        
        # Skill gap analysis across all viewed jobs
        viewed_jobs = StudentBehaviorLog.objects.filter(
            student=student, 
            action='viewed'
        ).values_list('job_id', flat=True)
        
        skill_demand = {}
        for job in Job.objects.filter(id__in=viewed_jobs):
            for skill in job.required_skills.all():
                skill_demand[skill.name] = skill_demand.get(skill.name, 0) + 1
        
        # Career trajectory prediction
        current_skills = [ss.skill.name for ss in StudentSkill.objects.filter(student=student)]
        trajectory = self._predict_trajectory(current_skills, student.projects.count())
        
        dashboard = {
            'profile_summary': {
                'trust_score': float(student.trust_score),
                'profile_complete': float(student.profile_complete_score) * 100,
                'next_milestone': self._get_next_milestone(student)
            },
            'applications': {
                'total': total_applications,
                'shortlisted': shortlisted,
                'interviews': interviews,
                'success_rate': (shortlisted / total_applications * 100) if total_applications > 0 else 0
            },
            'recommendations': recommendations[:10],  # Top 10
            'skill_analytics': {
                'most_demanded_missing_skills': sorted(skill_demand.items(), key=lambda x: x[1], reverse=True)[:5],
                'verified_skills_count': StudentSkill.objects.filter(student=student, verified_via__isnull=False).count()
            },
            'career_trajectory': trajectory,
            'recent_notifications': [
                {
                    'type': n.type,
                    'title': n.title,
                    'read': n.read,
                    'created_at': n.created_at.isoformat()
                } for n in Notification.objects.filter(
                    user_id=student.id, 
                    user_type='student'
                ).order_by('-created_at')[:5]
            ]
        }
        
        return JsonResponse({'status': 'success', 'data': dashboard})
    
    def _get_next_milestone(self, student):
        """Determine next profile improvement milestone"""
        if student.profile_complete_score < 0.8:
            return "Complete your profile to increase trust score"
        if student.projects.count() < 2:
            return "Add at least 2 projects with GitHub links"
        if StudentSkill.objects.filter(student=student, verified_via__isnull=True).count() > 0:
            return "Take skill assessments to verify your expertise"
        return "You're profile-ready! Start applying to recommended jobs"
    
    def _predict_trajectory(self, skills, project_count):
        """Simple rule-based career trajectory prediction"""
        tech_stacks = {
            'web_dev': ['JavaScript', 'React', 'Node.js', 'Python', 'Django'],
            'ai_ml': ['Python', 'TensorFlow', 'PyTorch', 'SQL', 'Statistics'],
            'mobile': ['Swift', 'Kotlin', 'React Native', 'Flutter'],
            'data': ['Python', 'SQL', 'Pandas', 'Tableau', 'AWS']
        }
        
        matches = {}
        for field, req_skills in tech_stacks.items():
            matches[field] = len(set(skills) & set(req_skills)) / len(req_skills)
        
        best_match = max(matches, key=matches.get)
        confidence = matches[best_match]
        
        roles = {
            'web_dev': ['Junior Full Stack', 'Full Stack Engineer', 'Senior Architect'],
            'ai_ml': ['ML Engineer Intern', 'Data Scientist', 'AI Researcher'],
            'mobile': ['Mobile Dev Intern', 'iOS/Android Developer', 'Mobile Lead'],
            'data': ['Data Analyst', 'Data Engineer', 'Analytics Manager']
        }
        
        stage = min(project_count // 3, 2)  # 0, 1, or 2
        
        return {
            'predicted_track': best_match,
            'confidence': f"{confidence*100:.1f}%",
            'current_stage': ['Entry', 'Mid-level', 'Senior'][stage],
            'next_role': roles[best_match][stage] if stage < 3 else 'Staff/Principal',
            'recommended_skills_to_add': list(set(tech_stacks[best_match]) - set(skills))[:3]
        }

class JobsListView(View):
    def get(self, request):
        """Get all active jobs"""
        jobs = Job.objects.filter(status='active').select_related('company')
        data = []
        for job in jobs:
            data.append({
                'id': str(job.id),
                'title': job.title,
                'company_name': job.company.name,
                'company_id': str(job.company.id),
                'job_type': job.job_type,
                'location': job.location,
                'min_cgpa': float(job.min_cgpa) if job.min_cgpa else None,
                'required_skills': [s.name for s in job.required_skills.all()],
                'salary_range': job.salary_range,
                'description': job.description[:200] + '...' if len(job.description) > 200 else job.description
            })
        return JsonResponse({'status': 'success', 'jobs': data})
@method_decorator(csrf_exempt, name='dispatch')  # Add this
class ApplyJobView(View):
    
    def post(self, request):
        """Manual job application"""
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=data['student_id'])
        job = get_object_or_404(Job, id=data['job_id'])
        
        # Check if already applied
        if Application.objects.filter(student=student, job=job).exists():
            return JsonResponse({'status': 'error', 'message': 'Already applied to this job'}, status=400)
        
        # Calculate match score
        engine = AIMatchingEngine(job.company)
        score, explanation = engine.calculate_match(student, job, save_explanation=True)
        
        application = Application.objects.create(
            student=student,
            job=job,
            match_score=score,
            status='applied',
            is_auto_applied=False
        )
        
        # Update job applicant count
        job.total_applicants += 1
        job.save()
        
        return JsonResponse({
            'status': 'success',
            'application_id': str(application.id),
            'match_score': score
        })

# ==================== COMPANY VIEWS ====================

class CompanyDashboardView(View):
    def get(self, request, company_id):
        company = get_object_or_404(Company, id=company_id)
        
        # Job postings analytics
        jobs = Job.objects.filter(company=company)
        job_stats = []
        
        for job in jobs:
            apps = Application.objects.filter(job=job)
            job_stats.append({
                'job_id': str(job.id),
                'title': job.title,
                'status': job.status,
                'total_applicants': apps.count(),
                'shortlisted': apps.filter(status='shortlisted').count(),
                'interviews': apps.filter(status='interview').count(),
                'hired': apps.filter(status='hired').count(),
                'avg_match_score': apps.aggregate(Avg('match_score'))['match_score__avg'] or 0
            })
        
        # AI Performance metrics
        feedback_logs = AIFeedbackLog.objects.filter(company=company)
        weight_evolution = [
            {
                'date': log.created_at.isoformat(),
                'previous': log.previous_weights,
                'adjusted': log.adjusted_weights
            } for log in feedback_logs.order_by('-created_at')[:5]
        ]
        
        # Top candidate recommendations for active jobs
        active_jobs = jobs.filter(status='active')
        top_candidates = []
        
        for job in active_jobs:
            engine = AIMatchingEngine(company)
            # Find best unmatched candidates
            candidates = Student.objects.exclude(
                applications__job=job
            ).order_by('-trust_score')[:20]
            
            best_matches = []
            for student in candidates:
                score, _ = engine.calculate_match(student, job, save_explanation=False)
                if score > 75:
                    best_matches.append({
                        'student_id': str(student.id),
                        'name': student.name,
                        'match_score': score,
                        'trust_score': float(student.trust_score)
                    })
            
            best_matches.sort(key=lambda x: x['match_score'], reverse=True)
            
            top_candidates.append({
                'job_id': str(job.id),
                'job_title': job.title,
                'recommended_candidates': best_matches[:5]
            })
        
        return JsonResponse({
            'status': 'success',
            'jobs': job_stats,
            'ai_weight_evolution': weight_evolution,
            'top_candidate_suggestions': top_candidates,
            'current_weights': company.get_weights()
        })
@method_decorator(csrf_exempt, name='dispatch')
class PostJobView(View):
    
    def post(self, request):
        data = json.loads(request.body)
        company = get_object_or_404(Company, id=data['company_id'])
        
        job = Job.objects.create(
            company=company,
            title=data['title'],
            description=data['description'],
            min_cgpa=data.get('min_cgpa'),
            job_type=data.get('job_type'),
            salary_range=data.get('salary_range', {}),
            location=data.get('location'),
            deadline=data.get('deadline')
        )
        
        # Add required skills
        for skill_name in data.get('required_skills', []):
            skill, _ = Skill.objects.get_or_create(
                name=skill_name,
                defaults={'category': 'Uncategorized'}
            )
            job.required_skills.add(skill)
        
        # Custom weights for this job type
        if data.get('custom_weights'):
            job.custom_weights = data['custom_weights']
            job.save()
        
        return JsonResponse({
            'status': 'success',
            'job_id': str(job.id),
            'message': 'Job posted successfully'
        })

class ApplicationsListView(View):
    def get(self, request):
        """Get applications for a specific job"""
        job_id = request.GET.get('job_id')
        if not job_id:
            return JsonResponse({'status': 'error', 'message': 'job_id required'}, status=400)
        
        applications = Application.objects.filter(job_id=job_id).select_related('student', 'job')
        data = []
        for app in applications:
            data.append({
                'id': str(app.id),
                'student_id': str(app.student.id),
                'student_name': app.student.name,
                'job_id': str(app.job.id),
                'job_title': app.job.title,
                'match_score': float(app.match_score) if app.match_score else 0,
                'status': app.status,
                'applied_at': app.applied_at.isoformat()
            })
        return JsonResponse({'status': 'success', 'applications': data})
@method_decorator(csrf_exempt, name='dispatch') 
class UpdateApplicationView(View):
    
    def post(self, request):
        """Update application status (shortlist, reject, etc.)"""
        data = json.loads(request.body)
        application = get_object_or_404(Application, id=data['application_id'])
        
        old_status = application.status
        application.status = data['status']
        application.save()
        
        # Create notification for student
        Notification.objects.create(
            user_id=application.student.id,
            user_type='student',
            type=f'status_{data["status"]}',
            title=f'Application {data["status"].title()}',
            message=f'Your application for {application.job.title} has been {data["status"]}',
            data={'job_id': str(application.job.id)}
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Application status updated to {data["status"]}'
        })
@method_decorator(csrf_exempt, name='dispatch') 
class ShortlistCandidatesView(View):
    
    def post(self, request):
        """Auto-shortlist top N candidates for a job"""
        data = json.loads(request.body)
        job = get_object_or_404(Job, id=data['job_id'])
        top_n = data.get('top_n', 10)
        
        # Get all applicants ranked by score
        applications = Application.objects.filter(
            job=job,
            status='applied'
        ).order_by('-match_score')[:top_n]
        
        shortlisted = []
        for app in applications:
            app.status = 'shortlisted'
            app.save()
            shortlisted.append({
                'application_id': str(app.id),
                'student_name': app.student.name,
                'match_score': float(app.match_score),
                'trust_score': float(app.student.trust_score)
            })
            
            # Notify student
            Notification.objects.create(
                user_id=app.student.id,
                user_type='student',
                type='shortlisted',
                title=f'Congratulations! Shortlisted for {job.title}',
                message=f'You have been shortlisted by {job.company.name} based on your match score of {app.match_score:.1f}%',
                data={'job_id': str(job.id)}
            )
        
        return JsonResponse({
            'status': 'success',
            'shortlisted_count': len(shortlisted),
            'candidates': shortlisted
        })
@method_decorator(csrf_exempt, name='dispatch')
class HireCandidateView(View):
    
    def post(self, request):
        """Mark candidate as hired and trigger weight adjustment"""
        data = json.loads(request.body)
        application = get_object_or_404(Application, id=data['application_id'])
        
        previous_status = application.status
        application.status = 'hired'
        application.save()
        
        # Trigger AI feedback loop
        engine = AIMatchingEngine(application.job.company)
        new_weights = engine.update_weights_from_feedback(
            application.job.company,
            application
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Candidate {application.student.name} marked as hired',
            'ai_adjusted': True,
            'new_weights': new_weights
        })

# ==================== ADMIN VIEWS ====================

class AdminAnalyticsView(View):
    def get(self, request):
        """System-wide analytics for admin"""
        
        # Platform metrics
        total_students = Student.objects.count()
        total_companies = Company.objects.count()
        total_jobs = Job.objects.count()
        total_applications = Application.objects.count()
        
        # Conversion funnel
        funnel = {
            'applied': Application.objects.filter(status='applied').count(),
            'shortlisted': Application.objects.filter(status='shortlisted').count(),
            'interview': Application.objects.filter(status='interview').count(),
            'hired': Application.objects.filter(status='hired').count()
        }
        
        # Fraud detection summary
        fraud_summary = {
            'total_flags': FraudFlag.objects.filter(resolved=False).count(),
            'by_severity': {
                'high': FraudFlag.objects.filter(severity='high', resolved=False).count(),
                'medium': FraudFlag.objects.filter(severity='medium', resolved=False).count(),
                'low': FraudFlag.objects.filter(severity='low', resolved=False).count()
            },
            'recent_flags': [
                {
                    'student': f.student.name,
                    'type': f.flag_type,
                    'severity': f.severity,
                    'date': f.created_at.isoformat()
                } for f in FraudFlag.objects.filter(resolved=False).order_by('-created_at')[:10]
            ]
        }
        
        # Skill demand analytics
        skill_demand = {}
        for job in Job.objects.all():
            for skill in job.required_skills.all():
                skill_demand[skill.name] = skill_demand.get(skill.name, {'count': 0, 'category': skill.category})
                skill_demand[skill.name]['count'] += 1
        
        top_skills = sorted(skill_demand.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
        
        # A/B Test results
        ab_results = self._calculate_ab_test_results()
        
        return JsonResponse({
            'platform_metrics': {
                'students': total_students,
                'companies': total_companies,
                'jobs': total_jobs,
                'applications': total_applications
            },
            'conversion_funnel': funnel,
            'fraud_detection': fraud_summary,
            'skill_demand': top_skills,
            'ab_test_results': ab_results
        })
    
    def _calculate_ab_test_results(self):
        """Compare control vs variant A algorithm performance"""
        control_hires = Application.objects.filter(
            student__ab_test_group='control',
            status='hired'
        ).count()
        control_total = Application.objects.filter(student__ab_test_group='control').count()
        
        variant_hires = Application.objects.filter(
            student__ab_test_group='variant_a',
            status='hired'
        ).count()
        variant_total = Application.objects.filter(student__ab_test_group='variant_a').count()
        
        control_rate = (control_hires / control_total * 100) if control_total > 0 else 0
        variant_rate = (variant_hires / variant_total * 100) if variant_total > 0 else 0
        
        return {
            'control_group': {
                'size': control_total,
                'hires': control_hires,
                'conversion_rate': f"{control_rate:.2f}%"
            },
            'variant_a': {
                'size': variant_total,
                'hires': variant_hires,
                'conversion_rate': f"{variant_rate:.2f}%"
            },
            'improvement': f"{((variant_rate - control_rate) / control_rate * 100):.1f}%" if control_rate > 0 else "N/A"
        }

class FraudFlagsListView(View):
    def get(self, request):
        """Get all unresolved fraud flags"""
        flags = FraudFlag.objects.filter(resolved=False).select_related('student')
        data = []
        for flag in flags:
            data.append({
                'id': str(flag.id),
                'student_id': str(flag.student.id),
                'student_name': flag.student.name,
                'flag_type': flag.flag_type,
                'severity': flag.severity,
                'details': flag.details,
                'created_at': flag.created_at.isoformat()
            })
        return JsonResponse({'status': 'success', 'flags': data})
@method_decorator(csrf_exempt, name='dispatch')  # Add this
class ResolveFraudFlagView(View):
    
    def post(self, request):
        data = json.loads(request.body)
        flag = get_object_or_404(FraudFlag, id=data['flag_id'])
        
        flag.resolved = True
        flag.reviewed_by = data.get('admin_id')
        flag.save()
        
        return JsonResponse({'status': 'success', 'message': 'Flag resolved'})

# ==================== NOTIFICATION & SCHEDULING ====================
@method_decorator(csrf_exempt, name='dispatch')
class NotificationsView(View):
    def get(self, request, user_id, user_type):
        notifications = Notification.objects.filter(
            user_id=user_id,
            user_type=user_type
        ).order_by('-created_at')
        
        return JsonResponse({
            'unread_count': notifications.filter(read=False).count(),
            'notifications': [
                {
                    'id': str(n.id),
                    'type': n.type,
                    'title': n.title,
                    'message': n.message,
                    'read': n.read,
                    'data': n.data,
                    'created_at': n.created_at.isoformat()
                } for n in notifications[:20]
            ]
        })
    
    @method_decorator(csrf_exempt)
    def post(self, request, user_id, user_type):
        """Mark as read"""
        data = json.loads(request.body)
        Notification.objects.filter(
            id__in=data.get('notification_ids', []),
            user_id=user_id
        ).update(read=True)
        
        return JsonResponse({'status': 'success'})
@method_decorator(csrf_exempt, name='dispatch')  # Add this
class ScheduleInterviewView(View):
    
    def post(self, request):
        data = json.loads(request.body)
        application = get_object_or_404(Application, id=data['application_id'])
        
        schedule = InterviewSchedule.objects.create(
            application=application,
            proposed_times=data.get('proposed_times', []),
            meeting_link=data.get('meeting_link', '')
        )
        
        # Update application status
        application.status = 'interview'
        application.save()
        
        # Notify student
        Notification.objects.create(
            user_id=application.student.id,
            user_type='student',
            type='interview_scheduled',
            title=f'Interview Scheduled: {application.job.title}',
            message=f'Proposed times: {", ".join(data["proposed_times"])}',
            data={
                'schedule_id': str(schedule.id),
                'meeting_link': data.get('meeting_link')
            }
        )
        
        return JsonResponse({
            'status': 'success',
            'schedule_id': str(schedule.id)
        })
        
class StudentMatchesView(View):
    def get(self, request, student_id):
        """Get job matches for a student with filtering"""
        student = get_object_or_404(Student, id=student_id)
        
        min_score = float(request.GET.get('min_score', 60))
        limit = int(request.GET.get('limit', 10))
        
        all_jobs = Job.objects.filter(status='active')
        matches = []
        
        for job in all_jobs:
            if not Application.objects.filter(student=student, job=job).exists():
                engine = AIMatchingEngine(job.company)
                score, explanation = engine.calculate_match(student, job, save_explanation=False)
                if score >= min_score:
                    matches.append({
                        'job_id': str(job.id),
                        'title': job.title,
                        'company': job.company.name,
                        'company_id': str(job.company.id),
                        'match_score': score,
                        'skill_gaps': explanation.get('missing_skills', []),
                        'salary': job.salary_range,
                        'location': job.location,
                        'job_type': job.job_type
                    })
        
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        
        return JsonResponse({
            'status': 'success',
            'matches': matches[:limit],
            'total_found': len(matches)
        })
        
def student_jobs(request):
    return render(request, 'student/jobs.html')

@method_decorator(csrf_exempt, name='dispatch')
class StudentLogoutView(View):
    def post(self, request):
        try:
            # Clear Django session
            if 'student_id' in request.session:
                del request.session['student_id']
            if 'user_type' in request.session:
                del request.session['user_type']
            request.session.flush()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Logged out successfully'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class CompanyLogoutView(View):
    def post(self, request):
        try:
            # Clear Django session
            if 'company_id' in request.session:
                del request.session['company_id']
            if 'user_type' in request.session:
                del request.session['user_type']
            request.session.flush()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Logged out successfully'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        

@method_decorator(csrf_exempt, name='dispatch')
class StudentLogoutView(View):
    def post(self, request):
        request.session.flush()
        return JsonResponse({'status': 'success'})

@method_decorator(csrf_exempt, name='dispatch')
class CompanyLogoutView(View):
    def post(self, request):
        request.session.flush()
        return JsonResponse({'status': 'success'})
    
@method_decorator(csrf_exempt, name='dispatch')
class AddSkillView(View):
    def post(self, request):
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=data['student_id'])
        
        skill, created = Skill.objects.get_or_create(
            name=data['skill_name'],
            defaults={'category': data.get('category', 'Uncategorized')}
        )
        
        student_skill, created = StudentSkill.objects.get_or_create(
            student=student,
            skill=skill,
            defaults={
                'proficiency_level': data['proficiency_level'],
                'verified_via': None
            }
        )
        
        if not created:
            student_skill.proficiency_level = data['proficiency_level']
            student_skill.save()
        
        return JsonResponse({'status': 'success', 'message': 'Skill added'})

@method_decorator(csrf_exempt, name='dispatch')
class AddExperienceView(View):
    def post(self, request):
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=data['student_id'])
        
        experience = WorkExperience.objects.create(
            student=student,
            company_name=data['company_name'],
            role=data['role'],
            start_date=data['start_date'],
            end_date=data.get('end_date'),
            is_current=data.get('is_current', False),
            description=data.get('description', '')
        )
        
        return JsonResponse({
            'status': 'success', 
            'experience_id': str(experience.id),
            'message': 'Experience added successfully'
        })
        
class UpdatePreferencesView(APIView):
    """Update student job preferences"""
    
    def post(self, request, student_id):
        try:
            student = get_object_or_404(Student, id=student_id)
            
            data = request.data.get('preferences', {})
            
            # Update preferences
            current_prefs = student.preferences or {}
            current_prefs.update({
                'job_types': data.get('job_types', current_prefs.get('job_types', [])),
                'company_size': data.get('company_size', current_prefs.get('company_size', [])),
                'salary_expectation': data.get('salary_expectation', current_prefs.get('salary_expectation', '')),
                'willing_to_relocate': data.get('willing_to_relocate', current_prefs.get('willing_to_relocate', False))
            })
            
            student.preferences = current_prefs
            student.save()
            
            return Response({
                'status': 'success',
                'message': 'Preferences updated successfully',
                'data': current_prefs
            })
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            
@method_decorator(csrf_exempt, name='dispatch') 
class StudentProfileView(View):
    
    @method_decorator(student_login_required)
    def get(self, request, student_id):
        student = get_object_or_404(Student, id=student_id)
        
        # Calculate current trust score
        student.calculate_trust_score()
        
        profile = {
            'id': str(student.id),
            'name': student.name,
            'email': student.email,
            'department': student.department,
            'cgpa': float(student.cgpa) if student.cgpa else None,
            'graduation_date': student.graduation_date.isoformat() if student.graduation_date else None,
            'university_id': student.university_id,
            'preferences': student.preferences,
            'github': {
                'username': student.github_username,
                'verified': student.github_verified,
                'score': student.github_score
            },
            'linkedin_url': student.linkedin_url,
            'portfolio_url': student.portfolio_url,
            'trust_score': float(student.trust_score),
            'profile_complete_score': float(student.profile_complete_score),
            'activity_score': float(student.activity_score),
            'skills': [
                {
                    'name': ss.skill.name,
                    'category': ss.skill.category,
                    'level': ss.proficiency_level,
                    'verified': ss.verified_via is not None
                } for ss in StudentSkill.objects.filter(student=student).select_related('skill')
            ],
            'projects': [
                {
                    'title': p.title,
                    'description': p.description,
                    'tech_stack': [s.name for s in p.tech_stack.all()],
                    'verified': p.verified,
                    'complexity': p.complexity_score,
                    'github_url': p.github_url
                } for p in student.projects.all()
            ],
            'experiences': [
                {
                    'company': e.company_name,
                    'role': e.role,
                    'duration': f"{e.start_date} to {e.end_date or 'Present'}",
                    'start_date': e.start_date.isoformat() if e.start_date else None,
                    'end_date': e.end_date.isoformat() if e.end_date else None,
                    'is_current': e.is_current,
                    'description': e.description,
                    'verified': e.verification_status == 'verified'
                } for e in student.experiences.all()
            ]
        }
        
        return JsonResponse({'status': 'success', 'data': profile})
    
    @method_decorator(csrf_exempt)
    def post(self, request):
        """Create new student profile"""
        try:
            data = json.loads(request.body)
            
            # Check if email already exists
            if Student.objects.filter(email=data.get('email')).exists():
                return JsonResponse({'status': 'error', 'message': 'Email already registered'}, status=400)
            
            student = Student.objects.create(
                email=data['email'],
                university_id=data.get('university_id', ''),
                name=data['name'],
                department=data.get('department', ''),
                cgpa=data.get('cgpa'),
                graduation_date=data.get('graduation_date'),
                preferences=data.get('preferences', {}),
                github_username=data.get('github_username', ''),
                linkedin_url=data.get('linkedin_url', ''),
                portfolio_url=data.get('portfolio_url', '')
            )
            student.set_password(data['password'])
            student.save()
            
            # Verify GitHub if provided
            if data.get('github_username'):
                validator = GitHubValidator()
                result = validator.validate_student_github(data['github_username'])
                if result['valid']:
                    student.github_verified = True
                    student.github_score = result['score']
                    student.save()
            
            # Calculate initial trust score
            student.calculate_trust_score()
            
            # Run fraud detection
            fraud_engine = FraudDetectionEngine()
            flags = fraud_engine.analyze_student(student)
            
            return JsonResponse({
                'status': 'success',
                'student_id': str(student.id),
                'trust_score': float(student.trust_score),
                'message': 'Registration successful'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    @method_decorator(csrf_exempt)
    def put(self, request, student_id):
        """UPDATE existing student profile - THIS IS THE KEY FIX"""
        try:
            data = json.loads(request.body)
            student = get_object_or_404(Student, id=student_id)
            
            # Update basic fields
            student.name = data.get('name', student.name)
            student.department = data.get('department', student.department)
            student.cgpa = data.get('cgpa', student.cgpa)
            student.university_id = data.get('university_id', student.university_id)
            student.graduation_date = data.get('graduation_date', student.graduation_date)
            student.github_username = data.get('github_username', student.github_username)
            student.linkedin_url = data.get('linkedin_url', student.linkedin_url)
            student.portfolio_url = data.get('portfolio_url', student.portfolio_url)
            
            # Update preferences
            if 'preferences' in data:
                current_prefs = student.preferences or {}
                current_prefs.update(data['preferences'])
                student.preferences = current_prefs
            
            student.save()
            
            # Handle Skills Update
            if 'skills' in data:
                # Remove existing skills not in new list
                existing_skill_names = [ss.skill.name for ss in StudentSkill.objects.filter(student=student)]
                new_skill_names = [s['name'] for s in data['skills']]
                
                # Delete removed skills
                StudentSkill.objects.filter(student=student).exclude(skill__name__in=new_skill_names).delete()
                
                # Add or update skills
                for skill_data in data['skills']:
                    skill, created = Skill.objects.get_or_create(
                        name=skill_data['name'],
                        defaults={'category': skill_data.get('category', 'Uncategorized')}
                    )
                    
                    student_skill, created = StudentSkill.objects.update_or_create(
                        student=student,
                        skill=skill,
                        defaults={
                            'proficiency_level': skill_data.get('level', 'Beginner'),
                            'verified_via': None  # Reset verification on update
                        }
                    )
            
            # Handle Experience Update
            if 'experiences' in data:
                # Clear existing experiences and recreate (simpler approach)
                student.experiences.all().delete()
                
                for exp_data in data['experiences']:
                    WorkExperience.objects.create(
                        student=student,
                        company_name=exp_data.get('company', ''),
                        role=exp_data.get('role', ''),
                        start_date=exp_data.get('start_date'),
                        end_date=exp_data.get('end_date') if not exp_data.get('is_current') else None,
                        is_current=exp_data.get('is_current', False),
                        description=exp_data.get('description', ''),
                        verification_status='pending'
                    )
            
            # Re-verify GitHub if username changed
            if data.get('github_username') and data.get('github_username') != student.github_username:
                validator = GitHubValidator()
                result = validator.validate_student_github(data['github_username'])
                if result['valid']:
                    student.github_verified = True
                    student.github_score = result['score']
                    student.save()
            
            # Recalculate trust score
            student.calculate_trust_score()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Profile updated successfully',
                'student_id': str(student.id),
                'trust_score': float(student.trust_score)
            })
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)