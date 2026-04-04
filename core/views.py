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
from django.contrib.auth.hashers import make_password, check_password
from .models import *
from .utils.ai_engine import AIMatchingEngine
from .utils.github_scraper import GitHubValidator
from .utils.fraud_detector import FraudDetectionEngine
from datetime import datetime, date, time
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
    # Get the company from session
    company_id = request.session.get('company_id')
    company = get_object_or_404(Company, id=company_id)
    
    return render(request, 'company/dashboard.html', {
        'company_name': company.name
    })
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
            student.activity_score = min(
                (student.activity_score or 0) + 5,  # +5 per login
                100
            )
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
        
        # Get career trajectory prediction
        current_skills = [ss.skill.name for ss in StudentSkill.objects.filter(student=student)]
        trajectory = self._predict_trajectory(current_skills, student.projects.count())
        
        profile = {
            'id': str(student.id),
            'name': student.name,
            'email': student.email,
            'department': student.department,
            'cgpa': float(student.cgpa) if student.cgpa else None,
            'graduation_date': student.graduation_date.isoformat() if student.graduation_date else None,
            'university_id': student.university_id,
            'student_id': student.university_id,  # Alias for frontend compatibility
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
            'total_applications': Application.objects.filter(student=student).count(),  # FIXED!
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
            ],
            'career_trajectory': trajectory  # ADDED: Career trajectory data
        }
        
        return JsonResponse({'status': 'success', 'data': profile})
    
    def _predict_trajectory(self, skills, project_count):
        """Simple rule-based career trajectory prediction - FIXED for case-insensitive matching"""
        tech_stacks = {
            'web_dev': ['JavaScript', 'React', 'Node.js', 'Python', 'Django', 'HTML', 'CSS', 'SQL', 'AWS', 'Docker'],
            'ai_ml': ['Python', 'TensorFlow', 'PyTorch', 'SQL', 'Statistics', 'AWS', 'Data Science'],
            'mobile': ['Swift', 'Kotlin', 'React Native', 'Flutter'],
            'data': ['Python', 'SQL', 'Pandas', 'Tableau', 'AWS']
        }
        
        # FIX: Convert user skills to lowercase for case-insensitive comparison
        skills_lower = [s.lower() for s in skills] if skills else []
        
        matches = {}
        for field, req_skills in tech_stacks.items():
            # FIX: Convert required skills to lowercase for comparison
            req_skills_lower = [s.lower() for s in req_skills]
            matches[field] = len(set(skills_lower) & set(req_skills_lower)) / len(req_skills)
        
        best_match = max(matches, key=matches.get)
        confidence = matches[best_match]
        
        roles = {
            'web_dev': ['Junior Full Stack', 'Full Stack Engineer', 'Senior Architect'],
            'ai_ml': ['ML Engineer Intern', 'Data Scientist', 'AI Researcher', 'ML Lead', 'DL Engineer'],
            'mobile': ['Mobile Dev Intern', 'iOS/Android Developer', 'Mobile Lead'],
            'data': ['Data Analyst', 'Data Engineer', 'Analytics Manager']
        }
        
        stage = min(project_count // 3, 2)  # 0, 1, or 2
        
        # FIX: Case-insensitive skill comparison for recommendations
        skills_lower_set = set(s.lower() for s in skills) if skills else set()
        recommended = [
            skill for skill in tech_stacks[best_match] 
            if skill.lower() not in skills_lower_set
        ][:3]

        return {
            'predicted_track': best_match,
            'confidence': f"{confidence*100:.1f}%",
            'current_stage': ['Entry', 'Mid-level', 'Senior'][stage],
            'next_role': roles[best_match][stage] if stage < 3 else 'Staff/Principal',
            'recommended_skills_to_add': recommended
        }

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
        """UPDATE existing student profile"""
        try:
            data = json.loads(request.body)
            
            print(f"Received data: {data}")
            print(f"Projects data: {data.get('projects', [])}")
            print(f"Experiences data: {data.get('experiences', [])}")
            
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
            
            # ==================== HANDLE SKILLS ====================
            if 'skills' in data:
                # Get current skill names
                current_skill_names = [ss.skill.name.lower() for ss in StudentSkill.objects.filter(student=student)]
                new_skills = data['skills']
                new_skill_names = [s['name'].lower() for s in new_skills]
                
                # Remove skills not in new list
                StudentSkill.objects.filter(student=student).exclude(skill__name__in=new_skill_names).delete()
                
                # Add or update skills
                for skill_data in new_skills:
                    skill_name = skill_data['name'].strip()
                    skill_name_lower = skill_name.lower()
                    
                    # Handle case where multiple skills exist with same name
                    try:
                        skill, created = Skill.objects.get_or_create(
                            name__iexact=skill_name_lower,
                            defaults={
                                'name': skill_name_lower,
                                'category': skill_data.get('category', 'Uncategorized')
                            }
                        )
                    except Skill.MultipleObjectsReturned:
                        skill = Skill.objects.filter(name__iexact=skill_name_lower).first()
                        created = False
                    
                    # Update skill name to lowercase for consistency
                    if skill.name != skill_name_lower:
                        skill.name = skill_name_lower
                        skill.save()
                    
                    StudentSkill.objects.update_or_create(
                        student=student,
                        skill=skill,
                        defaults={
                            'proficiency_level': skill_data.get('level', 'Beginner'),
                            'verified_via': None
                        }
                    )
            
            # ==================== HANDLE EXPERIENCES ====================
            if 'experiences' in data:
                # Clear all existing experiences and recreate
                student.experiences.all().delete()
                
                for exp_data in data['experiences']:
                    start_date = exp_data.get('start_date')
                    end_date = exp_data.get('end_date') if not exp_data.get('is_current') else None
                    is_current = exp_data.get('is_current', False)
                    
                    WorkExperience.objects.create(
                        student=student,
                        company_name=exp_data.get('company', ''),
                        role=exp_data.get('role', ''),
                        start_date=start_date,
                        end_date=end_date,
                        is_current=is_current,
                        description=exp_data.get('description', ''),
                        verification_status='pending'
                    )
            
            # ==================== HANDLE PROJECTS ====================
            if 'projects' in data:
                # Get current project titles for comparison
                current_titles = [p.title.lower() for p in student.projects.all()]
                new_projects = data['projects']
                
                # Build list of new titles to determine which to keep/delete
                new_titles = [p['title'].lower().strip() for p in new_projects]
                
                # Delete projects not in the new list
                student.projects.exclude(title__in=new_titles).delete()
                
                # Add or update projects
                for proj_data in new_projects:
                    title = proj_data.get('title', '').strip()
                    if not title:
                        continue
                    
                    # Parse tech stack
                    tech_stack = proj_data.get('tech_stack', [])
                    if isinstance(tech_stack, str):
                        tech_stack = [t.strip() for t in tech_stack.split(',') if t.strip()]
                    
                    github_url = proj_data.get('github_url', '')
                    description = proj_data.get('description', '')
                    complexity = proj_data.get('complexity', 3)
                    verified = proj_data.get('verified', False)
                    
                    # Try to get existing project by title
                    try:
                        project = student.projects.get(title__iexact=title)
                        project.description = description
                        project.github_url = github_url
                        project.complexity_score = complexity
                        project.verified = verified
                        project.save()
                    except Project.DoesNotExist:
                        project = Project.objects.create(
                            student=student,
                            title=title,
                            description=description,
                            github_url=github_url,
                            complexity_score=complexity,
                            verified=verified
                        )
                    
                    # Update tech stack
                    project.tech_stack.clear()
                    for tech_name in tech_stack:
                        if tech_name:
                            tech_clean = tech_name.strip().lower()
                            skill = Skill.objects.filter(name__iexact=tech_clean).first()
                            
                            if not skill:
                                skill = Skill.objects.create(
                                    name=tech_clean,
                                    category='Uncategorized'
                                )
                            else:
                                if skill.name != tech_clean:
                                    skill.name = tech_clean
                                    skill.save()
                            
                            project.tech_stack.add(skill)
            
            # Re-verify GitHub if username changed
            if data.get('github_username'):
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
        
        
        
@method_decorator(csrf_exempt, name='dispatch')
class AnalyzeMatchView(View):
    def post(self, request):
        """Analyze match between student and specific job"""
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=data['student_id'])
        job = get_object_or_404(Job, id=data['job_id'])
        
        # Get company weights
        engine = AIMatchingEngine(company=job.company, job=job)
        score, explanation = engine.calculate_match(student, job, save_explanation=False)
        
        # Log behavior (viewed analysis)
        StudentBehaviorLog.objects.create(
            student=student,
            job=job,
            action='viewed_analysis',
            duration_seconds=data.get('duration', 0)
        )
        student.activity_score = min(
            (student.activity_score or 0) + 2,  # +2 for analyzing jobs
            100
        )
        student.save()
        
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
                engine = AIMatchingEngine(company=job.company, job=job)
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
                'id': str(n.id),
                'type': n.type,
                'title': n.title,
                'message': n.message,
                'read': n.read,
                'created_at': n.created_at.isoformat(),
                'data': n.data  # Include the full data object
            } for n in Notification.objects.filter(
                user_id=student.id, 
                user_type='student'
            ).order_by('-created_at')[:10]
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
        
        # FIX: Case-insensitive skill comparison for recommendations
        skills_lower_set = set(s.lower() for s in skills) if skills else set()
        recommended = [
            skill for skill in tech_stacks[best_match] 
            if skill.lower() not in skills_lower_set
        ][:3]

        return {
            'predicted_track': best_match,
            'confidence': f"{confidence*100:.1f}%",
            'current_stage': ['Entry', 'Mid-level', 'Senior'][stage],
            'next_role': roles[best_match][stage] if stage < 3 else 'Staff/Principal',
            'recommended_skills_to_add': recommended
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
        engine = AIMatchingEngine(company=job.company, job=job)
        score, explanation = engine.calculate_match(student, job, save_explanation=True)
        
        application = Application.objects.create(
            student=student,
            job=job,
            match_score=score,
            status='applied',
            is_auto_applied=False
        )
        
        # ADD THESE LINES: Increase activity score for applying
        student.activity_score = min(
            (student.activity_score or 0) + 10,  # +10 for applying to jobs
            100
        )
        student.save()
        
        # Update job applicant count
        job.total_applicants += 1
        job.save()
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
            engine = AIMatchingEngine(company=company, job=job)
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
            'company_name': company.name,  # ← ADD THIS LINE
            'jobs': job_stats,
            'ai_weight_evolution': weight_evolution,
            'top_candidate_suggestions': top_candidates,
            'current_weights': company.get_weights()
        })
@method_decorator(csrf_exempt, name='dispatch')
class PostJobView(View):
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            # At the top of PostJobView.post()
            print(f"Received data: {data}")
            company = get_object_or_404(Company, id=data['company_id'])
            
            # ✅ FIX 1: Parse deadline string to datetime object
            deadline_str = data.get('deadline')
            deadline = None
            if deadline_str:
                from datetime import datetime
                # Handle both '2024-12-31' and '2024-12-31T00:00:00' formats
                try:
                    deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
                except ValueError:
                    deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
            
            job = Job.objects.create(
                company=company,
                title=data['title'],
                description=data['description'],
                min_cgpa=data.get('min_cgpa'),
                job_type=data.get('job_type'),
                salary_range=data.get('salary_range', {}),
                location=data.get('location'),
                deadline=deadline  # ✅ Now it's a datetime object or None
            )
            
            # ✅ FIX 2: Improved skill handling with proper error handling
            for skill_name in data.get('required_skills', []):
                skill_name_clean = skill_name.strip().lower()
                
                # Try to get existing skill first (case-insensitive)
                skill = Skill.objects.filter(name__iexact=skill_name_clean).first()
                
                if not skill:
                    # Create new skill if doesn't exist
                    skill = Skill.objects.create(
                        name=skill_name_clean,
                        category='Uncategorized'
                    )
                else:
                    # Normalize to lowercase
                    if skill.name != skill_name_clean:
                        skill.name = skill_name_clean
                        skill.save()
                
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
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return JsonResponse({
                'status': 'error', 
                'message': str(e)
            }, status=500)

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
@method_decorator(csrf_exempt, name='dispatch')
class ScheduleInterviewView(View):
    
    def post(self, request):
        data = json.loads(request.body)
        application = get_object_or_404(Application, id=data['application_id'])
        
        # Format the interview datetime
        interview_datetime = f"{data['date']} {data['start_time']}"
        
        schedule = InterviewSchedule.objects.create(
            application=application,
            proposed_times=[interview_datetime],
            meeting_link=data.get('meeting_link', ''),
            status='scheduled'
        )
        
        # Update application status
        application.status = 'interview'
        application.save()
        
        # Format date for display
        from datetime import datetime
        interview_date = datetime.strptime(data['date'], '%Y-%m-%d')
        formatted_date = interview_date.strftime('%A, %B %d, %Y')
        
        # Create notification for student with interview details
        Notification.objects.create(
            user_id=application.student.id,
            user_type='student',
            type='interview_scheduled',
            title=f'🎤 Interview Scheduled: {application.job.title}',
            message=f"""Your interview for {application.job.title} at {application.job.company.name} has been scheduled!

            📅 Date: {formatted_date}
            ⏰ Time: {data['start_time']} - {data['end_time']}
            🔗 Meeting Link: {data.get('meeting_link', 'To be shared separately')}

            Notes: {data.get('notes', 'No additional notes')}

            Please join on time. Good luck!""",
            data={
                'schedule_id': str(schedule.id),
                'meeting_link': data.get('meeting_link', ''),
                'interview_date': data['date'],
                'interview_time': data['start_time'],
                'job_title': application.job.title,
                'company_name': application.job.company.name
            }
        )
        
        return JsonResponse({
            'status': 'success',
            'schedule_id': str(schedule.id),
            'details': {
                'date': formatted_date,
                'time': f"{data['start_time']} - {data['end_time']}",
                'meeting_link': data.get('meeting_link', '')
            }
        })
class InterviewSlotAvailabilityView(View):
    """Get detailed slot availability for company"""
    
    def get(self, request, job_id):
        from core.models import InterviewSlot, ScheduledInterview  # Local imports
        
        try:
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            slots = InterviewSlot.objects.filter(job=job, is_active=True)
            
            slot_data = []
            for slot in slots:
                generated_slots = slot.generate_time_slots()
                
                # Get booked interviews for this slot
                booked = ScheduledInterview.objects.filter(
                    slot=slot
                ).select_related('application__student')
                
                booked_details = [{
                    'time': b.start_time.strftime('%H:%M'),
                    'student_name': b.application.student.name,
                    'student_id': str(b.application.student.id),
                    'interview_id': str(b.id),
                    'status': b.status
                } for b in booked]
                
                slot_data.append({
                    'slot_id': str(slot.id),
                    'date': slot.date.isoformat(),
                    'date_display': slot.date.strftime('%A, %B %d, %Y'),
                    'time_range': f"{slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}",
                    'all_slots': generated_slots,
                    'booked_count': len(booked),
                    'booked_details': booked_details,
                    'available_count': len([s for s in generated_slots if s['available']])
                })
            
            return JsonResponse({
                'status': 'success',
                'slots': slot_data
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
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
                engine = AIMatchingEngine(company=job.company, job=job)
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
        
        # FIXED: Normalize skill name to lowercase for case-insensitive matching
        skill_name_clean = data['skill_name'].strip().lower()
        
        # FIXED: Use case-insensitive lookup with iexact
        skill, created = Skill.objects.get_or_create(
            name__iexact=skill_name_clean,
            defaults={
                'name': skill_name_clean,  # Store as lowercase
                'category': data.get('category', 'Uncategorized')
            }
        )
        
        # If skill existed with different case, update to lowercase for consistency
        if not created and skill.name != skill_name_clean:
            skill.name = skill_name_clean
            skill.save()
        
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
        
        return JsonResponse({
            'status': 'success', 
            'message': 'Skill added',
            'skill_name': skill.name  # Return the normalized name
        })

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
        

        """UPDATE existing student profile"""
        try:
            data = json.loads(request.body)
            
             # ✅ THEN print it
            print(f"Received data: {data}")
            print(f"Projects data: {data.get('projects', [])}")
            print(f"Experiences data: {data.get('experiences', [])}")
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
            
            # ==================== HANDLE SKILLS ====================
            if 'skills' in data:
                # Get current skill names
                current_skill_names = [ss.skill.name.lower() for ss in StudentSkill.objects.filter(student=student)]
                new_skills = data['skills']
                new_skill_names = [s['name'].lower() for s in new_skills]
                
                # Remove skills not in new list
                StudentSkill.objects.filter(student=student).exclude(skill__name__in=new_skill_names).delete()
                
                # Add or update skills
                for skill_data in new_skills:
                    skill_name = skill_data['name'].strip()
                    skill_name_lower = skill_name.lower()
                    
                    # FIX: Handle case where multiple skills exist with same name (different cases)
                    try:
                        skill, created = Skill.objects.get_or_create(
                            name__iexact=skill_name_lower,
                            defaults={
                                'name': skill_name_lower,
                                'category': skill_data.get('category', 'Uncategorized')
                            }
                        )
                    except Skill.MultipleObjectsReturned:
                        # Multiple skills exist with same name (e.g., "Python" and "python")
                        # Get the first one and use it
                        skill = Skill.objects.filter(name__iexact=skill_name_lower).first()
                        # Optionally: merge/delete duplicates here
                        created = False
                    
                    # Update skill name to lowercase for consistency
                    if skill.name != skill_name_lower:
                        skill.name = skill_name_lower
                        skill.save()
                    
                    StudentSkill.objects.update_or_create(
                        student=student,
                        skill=skill,
                        defaults={
                            'proficiency_level': skill_data.get('level', 'Beginner'),
                            'verified_via': None
                        }
                    )
            
            # ==================== HANDLE EXPERIENCES (FIXED) ====================
            if 'experiences' in data:
                # Clear all existing experiences and recreate
                student.experiences.all().delete()
                
                for exp_data in data['experiences']:
                    # Parse dates properly
                    start_date = exp_data.get('start_date')
                    end_date = exp_data.get('end_date') if not exp_data.get('is_current') else None
                    is_current = exp_data.get('is_current', False)
                    
                    # Calculate duration string
                    if is_current:
                        duration = f"{start_date} to Present" if start_date else "Present"
                    else:
                        duration = f"{start_date} to {end_date}" if start_date and end_date else (start_date or "Unknown")
                    
                    WorkExperience.objects.create(
                        student=student,
                        company_name=exp_data.get('company', ''),  # FIXED: Use company_name field
                        role=exp_data.get('role', ''),
                        start_date=start_date,
                        end_date=end_date,
                        is_current=is_current,
                        description=exp_data.get('description', ''),
                        verification_status='pending'
                    )
            
            # ==================== HANDLE PROJECTS (FIXED) ====================
            
            if 'projects' in data:
                # Get current project titles for comparison
                current_titles = [p.title.lower() for p in student.projects.all()]
                new_projects = data['projects']
                
                # Build list of new titles to determine which to keep/delete
                new_titles = [p['title'].lower().strip() for p in new_projects]
                
                # Delete projects not in the new list
                student.projects.exclude(title__in=new_titles).delete()
                
                # Add or update projects
                for proj_data in new_projects:
                    title = proj_data.get('title', '').strip()
                    if not title:
                        continue  # Skip empty titles
                    
                    # Parse tech stack
                    tech_stack = proj_data.get('tech_stack', [])
                    if isinstance(tech_stack, str):
                        tech_stack = [t.strip() for t in tech_stack.split(',') if t.strip()]
                    
                    github_url = proj_data.get('github_url', '')
                    description = proj_data.get('description', '')
                    complexity = proj_data.get('complexity', 3)
                    verified = proj_data.get('verified', False)
                    
                    # Try to get existing project by title (case-insensitive)
                    try:
                        project = student.projects.get(title__iexact=title)
                        # Update existing
                        project.description = description
                        project.github_url = github_url
                        project.complexity_score = complexity
                        project.verified = verified
                        project.save()
                    except Project.DoesNotExist:
                        # Create new
                        project = Project.objects.create(
                            student=student,
                            title=title,
                            description=description,
                            github_url=github_url,
                            complexity_score=complexity,
                            verified=verified
                        )
                    
                    # Update tech stack - clear and rebuild
                    project.tech_stack.clear()
                    for tech_name in tech_stack:
                        if tech_name:
                            tech_clean = tech_name.strip().lower()
                            
                            # FIXED: Use filter().first() instead of get_or_create() with iexact
                            # This handles duplicate skills gracefully
                            skill = Skill.objects.filter(name__iexact=tech_clean).first()
                            
                            if not skill:
                                # Create new skill if doesn't exist
                                skill = Skill.objects.create(
                                    name=tech_clean,
                                    category='Uncategorized'
                                )
                            else:
                                # Update existing skill name to lowercase for consistency
                                if skill.name != tech_clean:
                                    skill.name = tech_clean
                                    skill.save()
                            
                            project.tech_stack.add(skill)
            
            # Re-verify GitHub if username changed
            if data.get('github_username'):
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
        
        
@method_decorator(csrf_exempt, name='dispatch')
class StudentApplicationsView(View):
    def get(self, request, student_id):
        """Get all jobs that a student has applied to"""
        student = get_object_or_404(Student, id=student_id)
        applications = Application.objects.filter(student=student).values_list('job_id', flat=True)
        return JsonResponse({
            'status': 'success',
            'applied_job_ids': [str(job_id) for job_id in applications]
        })
        
# ==================== SUPER ADMIN SETUP ====================
# ==================== SUPER ADMIN SETUP ====================
# Hardcoded super admin credentials
SUPER_ADMIN_EMAIL = "redwansamir90@gmail.com"
SUPER_ADMIN_PASSWORD = "samir7232"

def ensure_super_admin_exists():
    """Create super admin if not exists (hardcoded you) - handles missing table gracefully"""
    try:
        if not Admin.objects.filter(email=SUPER_ADMIN_EMAIL).exists():
            admin = Admin.objects.create(
                email=SUPER_ADMIN_EMAIL,
                is_super_admin=True
            )
            admin.set_password(SER_ADMIN_PASSWORD)
            admin.save()
            print(f"✅ Super admin created: {SUPER_ADMIN_EMAIL}")
    except Exception as e:
        # Table doesn't exist yet or other error - skip silently
        # This happens during migrations before table is created
        print(f"⚠️  Super admin check skipped (database not ready): {str(e)[:50]}...")
        pass

# DON'T call it here at module level - causes startup crash
# ensure_super_admin_exists()  <- REMOVE THIS LINE


# ==================== ADMIN AUTH VIEWS ====================
@method_decorator(csrf_exempt, name='dispatch')
class AdminLoginView(View):
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            email = data.get('email')
            password = data.get('password')
            
            # Check hardcoded super admin first
            if email == SUPER_ADMIN_EMAIL and password == SUPER_ADMIN_PASSWORD:
                ensure_super_admin_exists()
                admin = Admin.objects.get(email=SUPER_ADMIN_EMAIL)
                request.session['admin_id'] = str(admin.id)
                request.session['user_type'] = 'admin'
                request.session['is_super_admin'] = True
                
                return JsonResponse({
                    'status': 'success',
                    'admin_id': str(admin.id),
                    'email': admin.email,
                    'is_super_admin': True,
                    'redirect': '/admin/dashboard/'
                })
            
            # Check other admins in database
            admin = Admin.objects.filter(email=email).first()
            if admin and admin.check_password(password):
                request.session['admin_id'] = str(admin.id)
                request.session['user_type'] = 'admin'
                request.session['is_super_admin'] = admin.is_super_admin
                
                return JsonResponse({
                    'status': 'success',
                    'admin_id': str(admin.id),
                    'email': admin.email,
                    'is_super_admin': admin.is_super_admin,
                    'redirect': '/admin/dashboard/'
                })
            
            return JsonResponse({'status': 'error', 'message': 'Invalid credentials'}, status=401)
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class AddAdminView(View):
    """Only super admin can add new admins"""
    
    def post(self, request):
        try:
            # Verify super admin
            admin_id = request.session.get('admin_id')
            is_super = request.session.get('is_super_admin', False)
            
            if not admin_id or not is_super:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized - Super Admin only'}, status=403)
            
            data = json.loads(request.body)
            new_email = data.get('email')
            new_password = data.get('password')
            
            if not new_email or not new_password:
                return JsonResponse({'status': 'error', 'message': 'Email and password required'}, status=400)
            
            if Admin.objects.filter(email=new_email).exists():
                return JsonResponse({'status': 'error', 'message': 'Admin with this email already exists'}, status=400)
            
            # Create new admin
            new_admin = Admin.objects.create(
                email=new_email,
                is_super_admin=False,
                created_by_id=admin_id
            )
            new_admin.set_password(new_password)
            new_admin.save()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Admin {new_email} created successfully',
                'admin_id': str(new_admin.id)
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class AdminLogoutView(View):
    def post(self, request):
        request.session.flush()
        return JsonResponse({'status': 'success', 'message': 'Logged out'})


def admin_login_page(request):
    return render(request, 'admin/admin_login.html')

class ListAdminsView(View):
    """List all admins (super admin only)"""
    
    def get(self, request):
        admin_id = request.session.get('admin_id')
        is_super = request.session.get('is_super_admin', False)
        
        if not admin_id or not is_super:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        
        admins = Admin.objects.all().values('id', 'email', 'is_super_admin', 'created_at', 'created_by__email')
        return JsonResponse({
            'status': 'success',
            'admins': list(admins)
        })
        
@method_decorator(csrf_exempt, name='dispatch')
class CompanyWeightsView(View):
    def post(self, request, company_id):
        """Update company AI matching weights"""
        try:
            data = json.loads(request.body)
            company = get_object_or_404(Company, id=company_id)
            
            company.custom_weights = {
                'skills': float(data.get('skills', 0.4)),
                'cgpa': float(data.get('cgpa', 0.2)),
                'projects': float(data.get('projects', 0.2)),
                'activity': float(data.get('activity', 0.1)),
                'trust': float(data.get('trust', 0.1))
            }
            company.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Weights updated successfully',
                'weights': company.get_weights()
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
@method_decorator(csrf_exempt, name='dispatch')
class DeleteJobView(View):
    def delete(self, request, job_id):
        """Delete job and all associated applications"""
        try:
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            # Security check: ensure company owns this job
            if str(job.company.id) != company_id:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Unauthorized: You can only delete your own jobs'
                }, status=403)
            
            job_title = job.title
            deleted_applications_count = Application.objects.filter(job=job).count()
            
            # Delete all associated applications first (cascade)
            Application.objects.filter(job=job).delete()
            
            # Delete the job
            job.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Job "{job_title}" deleted successfully',
                'deleted_applications': deleted_applications_count
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)   
            
@method_decorator(csrf_exempt, name='dispatch')
class InterviewSlotView(View):
    """Manage interview slots for a job"""
    
    def get(self, request, job_id):
        """Get all interview slots for a job"""
        try:
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            # Security check
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            slots = InterviewSlot.objects.filter(job=job, is_active=True).order_by('date', 'start_time')
            
            data = []
            for slot in slots:
                data.append({
                    'slot_id': str(slot.id),
                    'date': slot.date.isoformat(),
                    'start_time': slot.start_time.strftime('%H:%M'),
                    'end_time': slot.end_time.strftime('%H:%M'),
                    'duration': slot.slot_duration_minutes,
                    'break_start': slot.break_start.strftime('%H:%M') if slot.break_start else None,
                    'break_end': slot.break_end.strftime('%H:%M') if slot.break_end else None,
                    'generated_slots': slot.generate_time_slots(),
                    'total_booked': ScheduledInterview.objects.filter(slot=slot).count()
                })
            
            return JsonResponse({'status': 'success', 'slots': data})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def post(self, request, job_id):
        """Create new interview slots"""
        try:
            data = json.loads(request.body)
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            # Create slot
            slot = InterviewSlot.objects.create(
                job=job,
                company=job.company,
                date=data['date'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                slot_duration_minutes=data.get('slot_duration_minutes', 30),
                break_start=data.get('break_start'),
                break_end=data.get('break_end')
            )
            
            return JsonResponse({
                'status': 'success',
                'slot_id': str(slot.id),
                'message': 'Interview slots created successfully',
                'available_slots': slot.generate_time_slots()
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ScheduleInterviewView(View):
    """Schedule interview for a shortlisted applicant"""
    
    def post(self, request, application_id):
        try:
            data = json.loads(request.body)
            application = get_object_or_404(Application, id=application_id)
            company_id = request.session.get('company_id')
            
            # Security check
            if str(application.job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            # Verify applicant is shortlisted
            if application.status != 'shortlisted':
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Applicant must be shortlisted before scheduling interview'
                }, status=400)
            
            # Check if interview already scheduled
            if hasattr(application, 'scheduled_interview'):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Interview already scheduled for this applicant'
                }, status=400)
            
            # Create interview
            interview = ScheduledInterview.objects.create(
                application=application,
                slot_id=data.get('slot_id'),
                date=data['date'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                meeting_link=data.get('meeting_link', ''),
                meeting_type=data.get('meeting_type', 'online'),
                company_notes=data.get('notes', '')
            )
            
            # Update application status
            application.status = 'interview'
            application.save()
            
            # Send notifications
            self._send_notifications(interview)
            
            return JsonResponse({
                'status': 'success',
                'interview_id': str(interview.id),
                'message': 'Interview scheduled successfully',
                'details': {
                    'date': interview.date.isoformat(),
                    'time': f"{interview.start_time.strftime('%H:%M')} - {interview.end_time.strftime('%H:%M')}",
                    'meeting_link': interview.meeting_link
                }
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def _send_notifications(self, interview):
        """Send notifications to both student and company"""
        app = interview.application
        
        # Notify Student
        Notification.objects.create(
            user_id=app.student.id,
            user_type='student',
            type='interview_scheduled',
            title=f'🎤 Interview Scheduled: {app.job.title}',
            message=(
                f'Your interview for {app.job.title} at {app.job.company.name} '
                f'is scheduled for {interview.date} at '
                f'{interview.start_time.strftime("%I:%M %p")} - {interview.end_time.strftime("%I:%M %p")}.\n\n'
                f'Meeting Link: {interview.meeting_link or "Will be shared soon"}'
            ),
            data={
                'interview_id': str(interview.id),
                'job_id': str(app.job.id),
                'date': interview.date.isoformat(),
                'start_time': interview.start_time.strftime('%H:%M'),
                'end_time': interview.end_time.strftime('%H:%M'),
                'meeting_link': interview.meeting_link
            }
        )
        
        # Notify Company
        Notification.objects.create(
            user_id=app.job.company.id,
            user_type='company',
            type='interview_scheduled',
            title=f'Interview Scheduled with {app.student.name}',
            message=(
                f'Interview scheduled for {app.student.name} '
                f'on {interview.date} at {interview.start_time.strftime("%I:%M %p")}'
            ),
            data={
                'interview_id': str(interview.id),
                'application_id': str(app.id),
                'student_id': str(app.student.id)
            }
        )
        
        interview.student_notified = True
        interview.company_notified = True
        interview.save()


@method_decorator(csrf_exempt, name='dispatch')
class AvailableSlotsView(View):
    """Get available time slots for a job (for scheduling dropdown)"""
    
    def get(self, request, job_id):
        try:
            job = get_object_or_404(Job, id=job_id)
            slots = InterviewSlot.objects.filter(
                job=job, 
                is_active=True,
                date__gte=timezone.now().date()
            ).order_by('date', 'start_time')
            
            available_slots = []
            for slot in slots:
                generated = slot.generate_time_slots()
                available = [s for s in generated if s['available']]
                
                if available:
                    available_slots.append({
                        'slot_id': str(slot.id),
                        'date': slot.date.isoformat(),
                        'date_display': slot.date.strftime('%A, %B %d, %Y'),
                        'time_slots': available
                    })
            
            return JsonResponse({
                'status': 'success',
                'available_slots': available_slots
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)    