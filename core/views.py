from django.http import Http404
from django.utils import timezone as django_timezone
from core.trajectory import display_github_username
import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Q, Avg, Count
from django.db import IntegrityError  # FIX: Import IntegrityError for proper error handling
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
from .utils.resume_parser import ResumeParser
from .utils.recruitment_agent import RecruitmentAgent
from datetime import datetime, date, time
from django.db import transaction

# ── Tech inference map: keyword in title/description → tech names to add ─────
# RULES:
#   1. Only infer for UNAMBIGUOUS keywords — if a word could belong to ANY tech stack,
#      do NOT infer. Better to leave tech_stack empty than to add the wrong tech.
#   2. Python is only inferred for domains where Python is the dominant language
#      (ML, AI, DL, NLP, Computer Vision, RL, Data Science). NOT for generic "web app".
#   3. Always infer the FRAMEWORK/LIBRARY when it's explicitly named
#      (django → python+django; flutter → flutter+dart; react → javascript+react).
#   4. Add mobile/web framework-specific entries so non-Python projects get their tech.
_TITLE_TECH_MAP = [

    # ── Python AI/ML/DL/NLP — Python is unambiguous for these domains ──────────
    (['rag system', 'retrieval augmented', 'langchain', 'llamaindex', 'vector store', 'embedding'],
     ['python', 'langchain', 'openai', 'faiss']),

    (['large language model', 'llm', ' gpt', 'language model', 'huggingface', 'transformers'],
     ['python', 'openai', 'langchain', 'transformers']),

    (['chatbot', 'medical chatbot', 'health chatbot', 'ai chatbot',
      'ai-powered', 'ai powered', 'lexical ai', 'tiny neuron', 'neuron research'],
     ['python', 'nlp', 'tensorflow']),

    (['natural language processing', 'nlp', 'text classification', 'named entity recognition',
      'sentiment analysis', 'text mining'],
     ['python', 'nlp', 'scikit-learn']),

    (['computer vision', 'image detection', 'object detection', 'face recognition',
      'image segmentation', 'yolo'],
     ['python', 'opencv', 'tensorflow']),

    (['deep learning', 'neural network', 'cnn ', 'rnn ', 'lstm', 'convolutional',
      'recurrent network', 'attention mechanism'],
     ['python', 'tensorflow', 'pytorch']),

    (['reinforcement learning', 'marl', 'multi-agent reinforcement', 'rl agent',
      'q-learning', 'policy gradient'],
     ['python', 'pytorch', 'tensorflow']),

    (['machine learning model', 'ml model', 'scikit', 'sklearn', 'xgboost', 'random forest',
      'data science pipeline', 'feature engineering',
      'early prediction', 'car health', 'health prediction',
      'smart transportation', 'traffic prediction', 'autonomous'],
     ['python', 'scikit-learn', 'pandas']),

    (['robotics', 'robotic arm', 'ros ', 'robot operating'],
     ['python', 'ros', 'arduino']),

    (['data analysis', 'data science', 'data pipeline', 'etl pipeline',
      'pandas', 'numpy', 'matplotlib', 'seaborn'],
     ['python', 'pandas', 'numpy']),

    # ── Explicit Python web frameworks — only when the framework name is present ─
    (['django', 'django rest', 'drf'],
     ['python', 'django']),
    (['flask app', 'flask api', 'flask web'],
     ['python', 'flask']),
    (['fastapi', 'fast api'],
     ['python', 'fastapi']),

    # ── Mobile: Flutter / React Native / Android / iOS ─────────────────────────
    (['flutter', 'dart '],
     ['flutter', 'dart']),
    (['react native'],
     ['javascript', 'react native']),
    (['android', 'kotlin', 'android studio'],
     ['android', 'kotlin', 'java']),
    (['ios app', 'swift ', 'swiftui', 'xcode'],
     ['ios', 'swift']),

    # ── Frontend JavaScript frameworks ──────────────────────────────────────────
    (['react.js', 'reactjs', 'react app', 'next.js', 'nextjs'],
     ['javascript', 'react']),
    (['vue.js', 'vuejs', 'nuxt'],
     ['javascript', 'vue']),
    (['angular', 'angularjs'],
     ['javascript', 'typescript', 'angular']),

    # ── Backend (non-Python) ────────────────────────────────────────────────────
    (['node.js', 'nodejs', 'express.js', 'expressjs'],
     ['javascript', 'nodejs']),
    (['spring boot', 'spring mvc', 'java backend'],
     ['java', 'spring']),
    (['laravel', 'php backend', 'php web'],
     ['php', 'laravel']),
    (['asp.net', 'dotnet', '.net core', 'c# web'],
     ['c#', 'dotnet']),

    # ── Database / Infrastructure (only when unambiguously named) ───────────────
    (['firebase', 'firestore'],
     ['firebase']),
    (['mongodb', 'mongoose'],
     ['mongodb']),
    (['postgresql', 'postgres'],
     ['postgresql']),
]

def _enrich_project_from_github(project, student):
    """
    If a project has a github_url, fetch repo details via GitHub API and:
      - Update tech_stack with actual repo languages (additive, won't remove existing)
      - Update complexity_score from repo signals (size, stars, languages, README)
      - Mark project.verified=True if the repo belongs to the student's github_username
    Safe to call even without a token — errors are caught and logged.
    """
    if not project.github_url:
        return

    try:
        from core.utils.github_scraper import GitHubValidator
        validator = GitHubValidator()

        # Extract owner/repo from URL: https://github.com/owner/repo[.git][/...]
        url = project.github_url.rstrip('/')
        # Remove .git suffix if present (e.g. https://github.com/user/repo.git)
        if url.endswith('.git'):
            url = url[:-4]
        parts = url.replace('https://github.com/', '').split('/')
        if len(parts) < 2:
            return
        repo_owner, repo_name = parts[0], parts[1]

        # Fetch full repo details (languages, README, stars, size)
        details = validator.fetch_repository_details(repo_owner, repo_name)
        if not details:
            return

        # 1. Update complexity_score from GitHub signals
        new_complexity = validator.calculate_project_complexity(details)
        if new_complexity > (project.complexity_score or 1):
            project.complexity_score = new_complexity

        # 2. Add detected languages to tech_stack (additive — don't clear existing)
        existing_tech = set(t.name.lower() for t in project.tech_stack.all())
        for lang in details.get('languages', {}).keys():
            lang_clean = lang.strip().lower()
            if lang_clean and lang_clean not in existing_tech:
                skill = Skill.objects.filter(name__iexact=lang_clean).first()
                if not skill:
                    skill = Skill.objects.create(name=lang_clean, category='Uncategorized')
                project.tech_stack.add(skill)
                existing_tech.add(lang_clean)

        # 3. Verify ownership — mark project verified if repo belongs to student
        # Normalize: treat underscore and hyphen as equivalent (samir_cyb == samir-cyb)
        def _norm(s): return s.lower().replace('-', '_').replace(' ', '_')
        student_gh = _norm(student.github_username or '')
        if student_gh and _norm(repo_owner) == student_gh:
            project.verified = True

        project.save()

    except Exception as e:
        pass  # Profile and provider content must not be logged.


def _infer_tech_from_text(title: str, description: str) -> list:
    """
    Return inferred tech list based on keywords in project title + description.

    Conservative: only adds tech when the keyword is domain-specific and unambiguous.
    Generic words like 'web app', 'dashboard', 'system', 'platform' are intentionally
    NOT in the map — they don't tell us which tech stack was used.
    """
    combined = (title + ' ' + description).lower()
    result = set()
    for keywords, techs in _TITLE_TECH_MAP:
        if any(kw in combined for kw in keywords):
            result.update(techs)
    return list(result)

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


@company_login_required
def company_skill_heatmap(request):
    company_id = request.session.get('company_id')
    return render(request, 'company/skill_heatmap.html', {'company_id': company_id})


@student_login_required
def student_skill_heatmap(request):
    """Student-facing skill demand heatmap — helps students know what to learn."""
    student_id = request.session.get('student_id')
    return render(request, 'student/skill_heatmap.html', {'student_id': student_id})


@company_login_required
def applicant_documents(request, application_id):
    """Show a student's CV and LinkedIn PDF to the company."""
    company_id = request.session.get('company_id')
    application = get_object_or_404(Application, id=application_id)

    # Security: only the job's company can view this
    if str(application.job.company.id) != company_id:
        return render(request, 'vetting/error.html', {'message': 'You are not authorized to view this applicant.'})

    student = application.student
    return render(request, 'company/applicant_documents.html', {
        'student': student,
        'application': application,
        'job': application.job,
    })


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

            # Validate required fields
            for field in ['name', 'email', 'password']:
                if not data.get(field):
                    return JsonResponse({'status': 'error', 'message': f'{field} is required'}, status=400)

            if Student.objects.filter(email=data['email']).exists():
                return JsonResponse({'status': 'error', 'message': 'Email already registered'}, status=400)

            # Build preferences from top-level form keys
            preferences = {
                'job_types':          data.get('job_types', []),
                'company_size':       data.get('company_size', []),
                'willing_to_relocate': data.get('willing_to_relocate', False),
            }

            student = Student.objects.create(
                email=data['email'],
                name=data['name'],
                university_id=data.get('university_id', ''),
                department=data.get('department', ''),
                cgpa=None if data.get('cgpa') in (None, '') else data['cgpa'],
                graduation_date=data.get('graduation_date') or None,
                github_username=data.get('github_username', ''),
                linkedin_url=data.get('linkedin_url', ''),
                portfolio_url=data.get('portfolio_url', ''),
                preferences=preferences,
            )
            student.set_password(data['password'])
            student.save()

            # Verify GitHub score if username provided
            if data.get('github_username'):
                try:
                    validator = GitHubValidator()
                    result = validator.validate_student_github(data['github_username'])
                    if result.get('valid'):
                        student.github_verified = True
                        student.github_score = result['score']
                        student.save()
                except Exception:
                    pass  # non-critical

            student.calculate_trust_score()

            # Auto-login after registration so they land on dashboard directly
            request.session.flush()
            request.session['student_id'] = str(student.id)
            request.session['user_type'] = 'student'

            return JsonResponse({
                'status': 'success',
                'student_id': str(student.id),
                'trust_score': float(student.trust_score),
                'message': 'Registration successful',
                'redirect': '/student/dashboard/',
            })

        except Exception as e:
            import traceback
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
            student.last_login = django_timezone.now()
            student.login_frequency += 1
            student.activity_score = min(
                (student.activity_score or 0) + 5,  # +5 per login
                100
            )
            student.save()
            
            # Create session
            request.session.flush()
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
            request.session.flush()
            
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
        from core.trajectory import trajectory_key
        from django.core.cache import cache
        trajectory = cache.get(trajectory_key(student)) or {}
        
        profile = {
            'id': str(student.id),
            'name': student.name,
            'email': student.email,
            'department': student.department,
            'cgpa': float(student.cgpa) if student.cgpa is not None else None,
            'graduation_date': student.graduation_date.isoformat() if student.graduation_date else None,
            'university_id': student.university_id,
            'student_id': student.university_id,  # Alias for frontend compatibility
            'preferences': student.preferences,
            'github': {
                'username': display_github_username(student.github_username),
                'verified': student.github_verified,
                'score': student.github_score
            },
            'linkedin_url': student.linkedin_url,
            'portfolio_url': student.portfolio_url,
            'behance_url': student.behance_url,
            'linkedin_score': student.linkedin_score or 0,
            'linkedin_parsed_data': student.linkedin_parsed_data or {},
            'department_category': student.department_category or student.get_department_category(),
            'certifications': student.certifications or [],
            'eca_activities': student.eca_activities or [],
            'research_papers': student.research_papers or [],
            'trust_score': float(student.trust_score),
            'profile_complete_score': float(student.profile_complete_score),
            'activity_score': float(student.activity_score),
            'total_applications': Application.objects.filter(student=student).count(),
            'skills': [
                {
                    'name': ss.skill.name,
                    'category': ss.skill.category,
                    'level': ss.proficiency_level,
                    'verified': ss.verified_via is not None,
                    'cross_validated': getattr(ss, 'cross_validated', False),
                    'source': getattr(ss, 'source', 'manual'),
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
    
    def _predict_trajectory(self, skills, project_count, student=None):
        """Gemini-powered career trajectory — uses skills + experience + applied jobs + skill gaps."""
        pass  # genai import removed — using llm_client centrally
        try:
            experiences = []
            applied_job_titles = []
            department = ''
            cgpa = None
            if student:
                department = student.department or ''
                cgpa = float(student.cgpa) if student.cgpa else None
                experiences = [
                    f"{e.role} at {e.company_name} ({e.start_date} – {e.end_date or 'Present'})"
                    for e in student.experiences.all()
                ]
                applied_job_titles = list(
                    Application.objects.filter(student=student)
                    .select_related('job')
                    .values_list('job__title', flat=True)[:20]
                )

            prompt = f"""You are a career trajectory AI. Analyze this student profile and return ONLY valid JSON.

STUDENT PROFILE:
- Department: {department}
- CGPA: {cgpa}
- Skills: {', '.join(skills) if skills else 'None listed'}
- Projects: {project_count} projects
- Experience: {'; '.join(experiences) if experiences else 'No experience listed'}
- Jobs Applied To: {', '.join(applied_job_titles) if applied_job_titles else 'None yet'}

Based on ALL of the above (not just skills), determine:
1. The most accurate career track for THIS specific student
2. Their current career stage
3. The most realistic next role title
4. Top 3 skills to add next
5. A 1-sentence career summary
6. A 6-month goal
7. A 1-year goal

Return ONLY this JSON (no markdown, no explanation):
{{
  "predicted_track": "short label like 'AI/ML Engineer' or 'Full Stack Developer' or 'Data Analyst' or 'Mobile Developer' or 'DevOps Engineer' or 'Backend Developer' etc.",
  "confidence": "High / Medium / Low",
  "current_stage": "Entry / Mid-level / Senior",
  "next_role": "specific job title",
  "recommended_skills_to_add": ["skill1", "skill2", "skill3"],
  "career_summary": "One sentence describing this student's career direction.",
  "goal_6_months": "Concrete 6-month goal",
  "goal_1_year": "Concrete 1-year goal"
}}"""

            from core.utils.llm_client import llm_generate as _llm_generate
            raw = _llm_generate(prompt).strip()
            if raw.startswith('```'):
                raw = raw.split('```')[1]
                if raw.startswith('json'):
                    raw = raw[4:]
            import json as _json
            result = _json.loads(raw.strip())
            return result
        except Exception as e:
            # Fallback: simple rule-based
            skills_lower = set(s.lower() for s in (skills or []))
            track_scores = {
                'Full Stack Developer': len(skills_lower & {'javascript','react','node.js','python','django','html','css'}),
                'AI/ML Engineer': len(skills_lower & {'python','tensorflow','pytorch','machine learning','data science','nlp'}),
                'Mobile Developer': len(skills_lower & {'swift','kotlin','flutter','react native','android','ios'}),
                'Data Analyst': len(skills_lower & {'sql','pandas','tableau','excel','power bi','statistics'}),
                'DevOps Engineer': len(skills_lower & {'docker','kubernetes','aws','ci/cd','linux','terraform'}),
            }
            best = max(track_scores, key=track_scores.get) if any(track_scores.values()) else 'Full Stack Developer'
            stage = ['Entry', 'Mid-level', 'Senior'][min(project_count // 3, 2)]
            return {
                'predicted_track': best,
                'confidence': 'Medium',
                'current_stage': stage,
                'next_role': f'Junior {best}',
                'recommended_skills_to_add': ['Docker', 'AWS', 'System Design'],
                'career_summary': f'Building towards a {best} career.',
                'goal_6_months': 'Complete 2 projects and earn a certification.',
                'goal_1_year': f'Land a junior {best} role.',
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
            
            
            student = get_object_or_404(Student, id=student_id)
            _old_gh_username = student.github_username or ''  # Capture BEFORE any field update

            # Update basic fields
            if 'name' in data:
                student.name = data['name'] or ''
            if 'department' in data:
                student.department = data['department'] or ''
            if 'cgpa' in data:
                student.cgpa = data['cgpa'] if data['cgpa'] not in ('', None) else None
            if 'university_id' in data:
                student.university_id = data['university_id'] or ''
            if 'graduation_date' in data:
                student.graduation_date = data['graduation_date'] if data['graduation_date'] not in ('', None) else None
            if 'github_username' in data:
                student.github_username = data['github_username'] or ''
            if 'linkedin_url' in data:
                student.linkedin_url = data['linkedin_url'] or ''
            if 'portfolio_url' in data:
                student.portfolio_url = data['portfolio_url'] or ''
            if 'behance_url' in data:
                student.behance_url = data['behance_url'] or ''

            if student.github_username != _old_gh_username:
                student.github_verified = False
                student.github_score = 0

            # Department-enrichment fields (non-tech)
            if 'certifications' in data and isinstance(data['certifications'], list):
                student.certifications = data['certifications']
            if 'eca_activities' in data and isinstance(data['eca_activities'], list):
                student.eca_activities = data['eca_activities']
            if 'research_papers' in data and isinstance(data['research_papers'], list):
                student.research_papers = data['research_papers']

            # Update preferences
            if 'preferences' in data:
                current_prefs = student.preferences or {}
                current_prefs.update(data['preferences'])
                student.preferences = current_prefs

            student.save()
            
            # ==================== HANDLE SKILLS ====================
            if 'skills' in data:
                new_skills = data['skills']
                new_skill_names_lower = [s.get('name', '').strip().lower() for s in new_skills if s.get('name')]
                
                # Remove skills not in new list (case-insensitive)
                student_student_skills = StudentSkill.objects.filter(student=student)
                for ss in student_student_skills:
                    if ss.skill.name.lower() not in new_skill_names_lower:
                        ss.delete()
                
                # Add or update skills
                for skill_data in new_skills:
                    skill_name = (skill_data.get('name') or '').strip()
                    if not skill_name:
                        continue
                    skill_name_lower = skill_name.lower()
                    
                    # Handle case where multiple skills exist with same name
                    try:
                        skill, created = Skill.objects.get_or_create(
                            name__iexact=skill_name_lower,
                            defaults={
                                'name': skill_name_lower,
                                'category': skill_data.get('category') or 'Uncategorized'
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
                            'proficiency_level': skill_data.get('level') or 'Beginner',
                            'verified_via': None
                        }
                    )
            
            # ==================== HANDLE EXPERIENCES ====================
            if 'experiences' in data:
                # Clear all existing experiences and recreate
                deleted_count = student.experiences.all().delete()[0]
                
                for exp_data in data['experiences']:
                    start_date = exp_data.get('start_date') or None
                    end_date = exp_data.get('end_date') if not exp_data.get('is_current') else None
                    is_current = exp_data.get('is_current', False)
                    
                    # FIX: Use `or ''` to handle None values from JSON (null -> None)
                    company_name = exp_data.get('company') or ''
                    role = exp_data.get('role') or ''
                    description = exp_data.get('description') or ''
                    
                    # Validate required fields
                    if not start_date:
                        continue
                    
                    WorkExperience.objects.create(
                        student=student,
                        company_name=company_name,
                        role=role,
                        start_date=start_date,
                        end_date=end_date,
                        is_current=is_current,
                        description=description,
                        verification_status='pending'
                    )
            
            # ==================== HANDLE PROJECTS ====================
            if 'projects' in data:
                new_projects = data['projects']
                
                # Build list of new titles (lowercase) for comparison
                new_titles_lower = []
                for p in new_projects:
                    title_raw = (p.get('title') or '').strip()
                    if title_raw:
                        new_titles_lower.append(title_raw.lower())
                
                
                # FIX: Delete projects not in the new list using CASE-INSENSITIVE matching
                projects_to_delete = []
                for existing_proj in student.projects.all():
                    if existing_proj.title.lower() not in new_titles_lower:
                        projects_to_delete.append(existing_proj.id)
                
                if projects_to_delete:
                    deleted = Project.objects.filter(id__in=projects_to_delete).delete()
                
                # Add or update projects
                for proj_data in new_projects:
                    title = (proj_data.get('title') or '').strip()
                    if not title:
                        continue
                    
                    # Parse tech stack
                    tech_stack = proj_data.get('tech_stack') or []
                    if isinstance(tech_stack, str):
                        tech_stack = [t.strip() for t in tech_stack.split(',') if t.strip()]
                    
                    # FIX: Use `or ''` instead of `.get('key', '')` to handle None/null values
                    # When AI returns {"description": null}, .get('description', '') returns None!
                    # But `or ''` catches both missing key AND null value.
                    github_url = proj_data.get('github_url') or ''
                    description = proj_data.get('description') or ''  # CRITICAL FIX
                    complexity = proj_data.get('complexity') or 3
                    verified = False  # Verification is assigned only by server-side checks.
                    
                    
                    # FIX: Robust project lookup/create with IntegrityError handling
                    # The problem: get_or_create(title__iexact=...) can fail because
                    # unique_together=['student','title'] is case-SENSITIVE in SQLite,
                    # so a project "My App" won't be found by title__iexact="my app"
                    # but creating "my app" will violate the unique constraint.
                    # Solution: First try case-insensitive lookup, then handle IntegrityError
                    project = None
                    created = False
                    old_github_url = None  # Track to skip API if URL unchanged

                    try:
                        # Step 1: Try to find existing project by case-insensitive title
                        project = student.projects.filter(title__iexact=title).first()

                        if project:
                            # Track old URL before overwriting
                            old_github_url = project.github_url or ''
                            # Update existing project
                            project.description = description
                            project.github_url = github_url or None
                            project.complexity_score = int(complexity)
                            project.verified = bool(project.verified and (old_github_url or '') == github_url)
                            project.save()
                            created = False
                        else:
                            # Step 2: No match found - create new project
                            # Wrap in try/except for IntegrityError (race condition or case-sensitive duplicate)
                            try:
                                project = Project.objects.create(
                                    student=student,
                                    title=title,
                                    description=description,
                                    github_url=github_url or None,
                                    complexity_score=int(complexity),
                                    verified=bool(verified),
                                )
                                created = True
                            except IntegrityError as ie:
                                # IntegrityError: unique_together constraint violated
                                # This means a project with this exact title already exists
                                # (maybe created in a race condition, or case-sensitive match)
                                # Try to find it again and update it
                                project = student.projects.filter(title=title).first()
                                if not project:
                                    # Try case-insensitive one more time
                                    project = student.projects.filter(title__iexact=title).first()
                                if project:
                                    project.description = description
                                    project.github_url = github_url or None
                                    project.complexity_score = int(complexity)
                                    project.verified = bool(project.verified and (old_github_url or '') == github_url)
                                    project.save()
                                else:
                                    # Should never happen, but handle gracefully
                                    continue
                    except Project.MultipleObjectsReturned:
                        # Edge case: multiple projects with same title (different case)
                        # Keep the first one, delete the rest
                        projects_qs = student.projects.filter(title__iexact=title).order_by('created_at')
                        project = projects_qs.first()
                        # Delete duplicates
                        duplicates = projects_qs.exclude(id=project.id)
                        dup_count = duplicates.count()
                        if dup_count > 0:
                            duplicates.delete()
                        
                        project.description = description
                        project.github_url = github_url or None
                        project.complexity_score = int(complexity)
                        project.verified = bool(project.verified and (old_github_url or '') == github_url)
                        project.save()
                    
                    # Update tech stack
                    if project:
                        # If Gemini returned empty tech_stack, infer from title+description
                        if not tech_stack:
                            tech_stack = _infer_tech_from_text(title, description)
                            if tech_stack:
                                pass  # Profile and provider content must not be logged.

                        project.tech_stack.clear()
                        for tech_name in tech_stack:
                            tech_clean = (tech_name or '').strip().lower()
                            if not tech_clean:
                                continue

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


                        # Enrich from GitHub ONLY if github_url is new or changed
                        new_github_url = github_url or ''
                        if new_github_url and new_github_url != (old_github_url or ''):
                            _enrich_project_from_github(project, student)
                        elif new_github_url:
                            pass  # Profile and provider content must not be logged.

            # Re-verify GitHub ONLY if username changed or not yet verified
            new_gh_username = data.get('github_username', '')
            if new_gh_username and (new_gh_username != _old_gh_username or not student.github_verified):
                try:
                    validator = GitHubValidator()
                    result = validator.validate_student_github(new_gh_username)
                    if result.get('valid'):
                        student.github_verified = True
                        student.github_score = result.get('score', 0)
                        student.save()

                        # ── Auto-verify student's projects from GitHub ────────
                        # A project whose github_url belongs to this student → verified = True
                        def _norm_gh(s):
                            return (s or '').lower().replace('-', '_').replace(' ', '_')

                        gh_owner_norm = _norm_gh(new_gh_username)
                        _verified_count = 0
                        for proj in student.projects.filter(
                            github_url__isnull=False
                        ).exclude(github_url=''):
                            url = proj.github_url.strip().rstrip('/').rstrip('.git').lower()
                            if 'github.com/' in url:
                                parts = url.split('github.com/')[-1].split('/')
                                if parts and _norm_gh(parts[0]) == gh_owner_norm:
                                    if not proj.verified:
                                        proj.verified = True
                                        proj.save(update_fields=['verified'])
                                        _verified_count += 1

                        # ── Cross-validate student skills from GitHub languages ─
                        # If GitHub confirms Dart/Flutter → mark matching StudentSkill
                        # as cross_validated so Trust Score gets the depth bonus.
                        _cross_val_count = 0
                        suggested_skills = result.get('suggested_skills', [])
                        for skill_name in suggested_skills:
                            qs = StudentSkill.objects.filter(
                                student=student,
                                skill__name__iexact=skill_name,
                            ).select_related('skill')
                            for ss in qs:
                                if not ss.cross_validated:
                                    ss.cross_validated = True
                                    ss.save(update_fields=['cross_validated'])
                                    _cross_val_count += 1

                        # ─────────────────────────────────────────────────────

                except Exception as gh_err:
                    pass  # Profile and provider content must not be logged.
            
            # Recalculate trust score
            student.calculate_trust_score()

            # ── Activity tracking: meaningful profile update ───────────────
            student.activity_score = min(float(student.activity_score or 0) + 5, 100)
            student.save(update_fields=['activity_score'])
            # ─────────────────────────────────────────────────────────────

            # Award leaderboard points based on current profile state
            try:
                from .utils.points import award_points
                if StudentSkill.objects.filter(student=student).exists():
                    award_points(student, 'add_skill')
                if Project.objects.filter(student=student).exists():
                    award_points(student, 'add_project')
                if float(student.profile_complete_score or 0) >= 0.80:
                    award_points(student, 'profile_complete')
            except Exception:
                pass

            # Invalidate trajectory cache so next dashboard load regenerates it
            try:
                prefs = student.preferences or {}
                prefs.pop('_trajectory_cache', None)
                student.preferences = prefs
                student.save(update_fields=['preferences'])
            except Exception:
                pass

            return JsonResponse({
                'status': 'success',
                'message': 'Profile updated successfully',
                'student_id': str(student.id),
                'trust_score': float(student.trust_score)
            })
            
        except Exception as e:
            import traceback
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        
        
        
@method_decorator(csrf_exempt, name='dispatch')
class DebugStudentScoresView(View):
    """
    Debug endpoint — returns a full breakdown of Activity and Trust scores
    for a student, showing exactly what each signal contributed.

    Usage: GET /api/debug/student-scores/?student_id=<uuid>

    Response includes:
      - activity.final          : 0–100 final activity score
      - activity.breakdown      : signal-by-signal point breakdown
      - activity.raw_pts        : total raw points before capping
      - trust.final             : 0–100 final trust score
      - trust.breakdown         : signal-by-signal point breakdown
      - trust.raw_pts           : total raw points before capping
      - trust._profile_fields   : which profile fields are filled
      - trust._skill_detail     : expert/intermediate/cv'd skill counts
      - trust._ext_detail       : dept-specific external signals detail
      - stored_trust_score      : value stored on Student model
      - stored_activity_score   : value stored on Student model
    """
    def get(self, request):
        student_id = request.GET.get('student_id')
        if not student_id:
            return JsonResponse({'error': 'student_id required'}, status=400)

        student = get_object_or_404(Student, id=student_id)

        from .utils.ai_engine import AIMatchingEngine
        engine = AIMatchingEngine()

        activity_score = engine.calculate_activity_score(student)
        trust_score    = engine.calculate_trust_score_dept_aware(student)

        # Optional: job-aware project scoring when ?job_id=... is provided
        job_id = request.GET.get('job_id')
        debug_job = None
        if job_id:
            try:
                debug_job = Job.objects.get(id=job_id)
            except (Job.DoesNotExist, Exception):
                pass

        project_score = engine.calculate_project_score(student, job=debug_job)

        activity_breakdown = getattr(student, '_activity_breakdown', {})
        trust_breakdown    = getattr(student, '_trust_breakdown', {})
        project_breakdown  = getattr(student, '_project_breakdown', {})

        return JsonResponse({
            'status': 'ok',
            'student': {
                'id':         str(student.id),
                'name':       student.name,
                'department': student.department,
                'dept_cat':   student.department_category or student.get_department_category(),
            },
            'activity': {
                'final':     round(activity_score * 100, 1),
                'raw_pts':   getattr(student, '_activity_raw', 0),
                'breakdown': activity_breakdown,
                'stored':    float(student.activity_score),
                'note': (
                    'Activity is computed live from DB. '
                    '"stored" is the legacy counter; "final" is what the match engine uses.'
                ),
            },
            'trust': {
                'final':     round(trust_score * 100, 1),
                'raw_pts':   getattr(student, '_trust_raw', 0),
                'breakdown': {
                    k: v for k, v in trust_breakdown.items()
                    if not k.startswith('_')
                },
                'detail': {
                    k: v for k, v in trust_breakdown.items()
                    if k.startswith('_')
                },
                'stored':    float(student.trust_score),
                'note': (
                    'Trust is computed live from DB each time a match is scored. '
                    '"stored" is refreshed when the student updates their profile.'
                ),
            },
            'projects': {
                'final':          round(project_score * 100, 1),
                'mode':           project_breakdown.get('mode', 'unknown'),
                'job_context':    str(debug_job) if debug_job else None,
                'job_id':         job_id or None,
                'total_projects': project_breakdown.get('total_projects', 0),
                'job_skills':     project_breakdown.get('job_skills', []),
                'top_3_used':     project_breakdown.get('top_3_used', []),
                'all_projects':   project_breakdown.get('all_projects', []),
                'weighted_sum':   project_breakdown.get('weighted_sum', 0),
                'depth_bonus':    project_breakdown.get('depth_bonus', 0),
                'note': (
                    'Job-aware scoring when ?job_id= is provided. '
                    'Each project gets: relevance × complexity × verification_multiplier. '
                    'Top-3 projects are used. GitHub-verified = 1.5×, manual = 1.2×.'
                    if debug_job else
                    'Complexity-based fallback (no job context). '
                    'Add ?job_id=<uuid> to see job-relevant project scoring.'
                ),
            },
            'signal_summary': {
                'activity_signals': [
                    {'signal': 'vetting_tests',        'pts': activity_breakdown.get('vetting_tests', 0),        'max': 25, 'desc': 'Completed×8 + passed×5'},
                    {'signal': 'application_quality',  'pts': activity_breakdown.get('application_quality', 0),  'max': 20, 'desc': 'Shortlisted/hired ratio'},
                    {'signal': 'login_regularity',     'pts': activity_breakdown.get('login_regularity', 0),     'max': 15, 'desc': 'login_frequency / 20 × 15'},
                    {'signal': 'ai_interviews',        'pts': activity_breakdown.get('ai_interviews', 0),        'max': 15, 'desc': 'Completed AI interviews × 8'},
                    {'signal': 'profile_freshness',    'pts': activity_breakdown.get('profile_freshness', 0),    'max': 10, 'desc': 'Days since last profile update'},
                    {'signal': 'certifications',       'pts': activity_breakdown.get('certifications', 0),       'max': 10, 'desc': '× 3 per cert'},
                    {'signal': 'spam_penalty',         'pts': activity_breakdown.get('spam_penalty', 0),         'max': 0,  'desc': '−1 per excess app with 0 success'},
                ],
                'trust_signals': [
                    {'signal': 'profile_completeness', 'pts': trust_breakdown.get('profile_completeness', 0), 'max': 20, 'desc': '7 required fields'},
                    {'signal': 'vetting_passed',       'pts': trust_breakdown.get('vetting_passed', 0),       'max': 25, 'desc': 'Passed tests × 8'},
                    {'signal': 'skill_depth',          'pts': trust_breakdown.get('skill_depth', 0),          'max': 15, 'desc': 'Expert×4 + Intermediate×2 + CV\'d×2'},
                    {'signal': 'external_validation',  'pts': trust_breakdown.get('external_validation', 0),  'max': 25, 'desc': 'Dept-specific: GitHub/LinkedIn/Portfolio/Papers/ECA'},
                    {'signal': 'documents',            'pts': trust_breakdown.get('documents', 0),            'max': 10, 'desc': 'CV uploaded + LinkedIn PDF score'},
                    {'signal': 'certifications',       'pts': trust_breakdown.get('certifications', 0),       'max':  5, 'desc': '1 pt per cert, max 5'},
                    {'signal': 'spam_penalty',         'pts': trust_breakdown.get('spam_penalty', 0),         'max':  0, 'desc': '−1 per excess app (>15) with 0 success'},
                ],
            },
        })


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
        try:
            return self._get_dashboard(request, student_id)
        except Http404:
            return JsonResponse({'status': 'error', 'message': 'Student not found'}, status=404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    def _get_dashboard(self, request, student_id):
        student = get_object_or_404(Student, id=student_id)

        # Pre-fetch all active jobs (capped at 200 for performance)
        all_active_jobs = list(
            Job.objects.filter(status='active')
            .select_related('company')
            .prefetch_related('required_skills')
            .order_by('-created_at')[:200]
        )

        # Get IDs of jobs already applied to
        applied_job_ids = set(
            Application.objects.filter(student=student).values_list('job_id', flat=True)
        )

        # Student's existing skills (for gap analysis)
        student_skills = set(
            ss.skill.name.lower()
            for ss in StudentSkill.objects.filter(student=student).select_related('skill')
        )

        # ── Composite match scoring (skill + CGPA + experience + projects) ──
        # Weights: skills 50%, cgpa 25%, experience 15%, projects 10%
        student_cgpa = float(student.cgpa or 0)
        student_exp  = min(float(getattr(student, 'years_experience', 0) or 0), 5) / 5

        # Precompute project tech_stack sets for job-aware lightweight scoring
        # (avoids per-job DB queries — one prefetch for all dashboard recommendations)
        from core.utils.ai_engine import PROJECT_TECH_IMPLIES as _IMPLIES
        _all_projects = list(student.projects.prefetch_related('tech_stack').all())
        student_projects_fallback = min(len(_all_projects), 5) / 5   # count-based fallback

        # Direct tech_stack skills across all student projects
        _student_proj_direct = set()
        for _proj in _all_projects:
            for _sk in _proj.tech_stack.all():  # uses prefetch cache
                _student_proj_direct.add(_sk.name.lower())

        # Expand with implied skills (one level deep)
        _student_proj_implied = set()
        for _tech in _student_proj_direct:
            for _imp in _IMPLIES.get(_tech, []):
                _student_proj_implied.add(_imp.lower())

        recommendations = []
        for job in all_active_jobs:
            if job.id in applied_job_ids:
                continue

            job_skills = {s.name.lower() for s in job.required_skills.all()}

            # Skill score (50%)
            if job_skills:
                overlap = student_skills & job_skills
                skill_score = len(overlap) / len(job_skills)
            else:
                skill_score = 0.5  # neutral when job has no required skills

            # Hard gate: zero skill overlap with a job that has required skills = disqualified
            if job_skills and skill_score == 0:
                continue

            # CGPA score (25%) — compare against job's min_cgpa or 3.0 default
            min_cgpa = float(job.min_cgpa or 3.0)
            cgpa_score = min(student_cgpa / max(min_cgpa, 0.1), 1.0) if min_cgpa > 0 else 1.0

            # Experience score (15%)
            exp_score = student_exp

            # Projects score (10%) — job-relevant with implied knowledge (lightweight)
            if job_skills and (_student_proj_direct or _student_proj_implied):
                _direct_overlap = len(_student_proj_direct & job_skills)
                _implied_overlap = len(
                    _student_proj_implied & (job_skills - _student_proj_direct)
                )
                proj_score = min(
                    (_direct_overlap + _implied_overlap * 0.5) / len(job_skills),
                    1.0,
                )
            else:
                proj_score = student_projects_fallback

            composite = round(
                (skill_score * 0.50 + cgpa_score * 0.25 + exp_score * 0.15 + proj_score * 0.10) * 100,
                1
            )

            # Only show jobs with ≥ 60% match (same threshold as apply eligibility)
            if composite < 60:
                continue

            recommendations.append({
                'job_id': str(job.id),
                'title': job.title,
                'company': job.company.name,
                'match_score': composite,
                'skill_gaps': len(job_skills - student_skills) if job_skills else 0,
                'salary': job.salary_range
            })
        recommendations.sort(key=lambda x: x['match_score'], reverse=True)

        # ── Analytics ─────────────────────────────────────────────────────────
        total_applications = Application.objects.filter(student=student).count()
        shortlisted = Application.objects.filter(student=student, status='shortlisted').count()
        interviews  = Application.objects.filter(student=student, status='interview').count()

        # ── Skill gap analysis: use ALL active jobs (not just viewed ones) ───
        # Count how often each required skill appears across active jobs,
        # then filter to skills the student doesn't have.
        skill_demand = {}
        for job in all_active_jobs:
            for skill in job.required_skills.all():
                if skill.name.lower() not in student_skills:
                    skill_demand[skill.name] = skill_demand.get(skill.name, 0) + 1
        
        # Load the same forecast independently so an offline AI service cannot
        # block the dashboard's profile/application data.
        from core.trajectory import trajectory_key
        from django.core.cache import cache
        trajectory = cache.get(trajectory_key(student)) or {}
        
        # Recompute trust score using the same dept-aware formula the agent uses,
        # so the dashboard and applicant view always show the same number.
        try:
            from core.utils.ai_engine import AIMatchingEngine as _AME
            _live_trust = round(_AME().calculate_trust_score_dept_aware(student) * 100)
            # Persist so other reads stay consistent
            student.trust_score = _live_trust
            student.save(update_fields=['trust_score'])
        except Exception:
            _live_trust = float(student.trust_score)

        dashboard = {
            'profile_summary': {
                'name': student.name,
                'trust_score': _live_trust,
                'profile_complete': float(student.profile_complete_score) * 100,
                'next_milestone': self._get_next_milestone(student)
            },
            'applications': {
                'total': total_applications,
                'shortlisted': shortlisted,
                'interviews': interviews,
                'success_rate': (shortlisted / total_applications * 100) if total_applications > 0 else 0
            },
            'recommendations': recommendations[:50],
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
                'created_at': n.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),  # Always UTC with Z
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
    
    def _predict_trajectory(self, skills, project_count, student=None):
        """Delegate to StudentProfileView._predict_trajectory (Gemini-powered)."""
        return StudentProfileView()._predict_trajectory(skills, project_count, student=student)

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

        # Enforce 60% eligibility threshold
        if score < 60:
            return JsonResponse({
                'status': 'error',
                'message': f'Your match score ({round(score)}%) is below the 60% minimum required to apply for this job.'
            }, status=400)

        application = Application.objects.create(
            student=student,
            job=job,
            match_score=score,
            status='applied',
            is_auto_applied=False
        )

        # Increase activity score for applying
        student.activity_score = min((student.activity_score or 0) + 10, 100)
        student.save()

        # Update job applicant count
        # Applicant counters are maintained by Application signals.

        # ── Email confirmation ───────────────────────────────────────────────
        try:
            from .utils.email_helpers import send_application_confirmation_email
            send_application_confirmation_email(application)
        except Exception:
            pass

        # ── Notify company of new application ───────────────────────────────
        try:
            Notification.objects.create(
                user_id=job.company.id,
                user_type='company',
                type='new_application',
                title=f'📋 New Application: {job.title}',
                message=f'{student.name} applied to {job.title} with a {round(score)}% match score.',
                data={
                    'student_id':     str(student.id),
                    'student_name':   student.name,
                    'job_id':         str(job.id),
                    'job_title':      job.title,
                    'match_score':    round(score, 1),
                    'application_id': str(application.id),
                }
            )
        except Exception:
            pass

        # ── Auto-trigger Recruitment Agent ──────────────────────────────────
        try:
            agent = RecruitmentAgent(company=job.company)
            agent.run(application, triggered_by='auto')
        except Exception as agent_err:
            import logging
            logging.getLogger(__name__).warning(f"RecruitmentAgent auto-run failed: {agent_err}")

        return JsonResponse({
            'status': 'success',
            'application_id': str(application.id),
            'match_score': score
        })

# ==================== COMPANY VIEWS ====================

class CompanyDashboardView(View):
    def get(self, request, company_id):
        company = get_object_or_404(Company, id=company_id)

        # ── Job stats: one aggregated query instead of N+1 ──────────────────
        jobs = list(Job.objects.filter(company=company))
        job_ids = [j.id for j in jobs]

        from django.db.models import Count, Avg, Q
        app_agg = (
            Application.objects
            .filter(job_id__in=job_ids)
            .values('job_id')
            .annotate(
                total=Count('id'),
                shortlisted=Count('id', filter=Q(status='shortlisted')),
                interviews=Count('id', filter=Q(status='interview')),
                hired=Count('id', filter=Q(status='hired')),
                avg_score=Avg('match_score'),
            )
        )
        agg_by_job = {str(r['job_id']): r for r in app_agg}

        job_stats = []
        for job in jobs:
            agg = agg_by_job.get(str(job.id), {})
            job_stats.append({
                'job_id': str(job.id),
                'title': job.title,
                'status': job.status,
                'total_applicants': agg.get('total', 0),
                'shortlisted': agg.get('shortlisted', 0),
                'interviews': agg.get('interviews', 0),
                'hired': agg.get('hired', 0),
                'avg_match_score': round(float(agg.get('avg_score') or 0), 1),
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

        # ── Top candidates: fast skill-overlap (no AI engine loop) ──────────
        active_jobs = [j for j in jobs if j.status == 'active']
        top_candidates = []

        # Pre-fetch all student skills in bulk
        all_student_skills = (
            StudentSkill.objects
            .select_related('skill', 'student')
            .values('student_id', 'skill__name')
        )
        student_skill_map = {}
        for row in all_student_skills:
            sid = str(row['student_id'])
            student_skill_map.setdefault(sid, set()).add((row['skill__name'] or '').lower())

        for job in active_jobs:
            job_skills = {s.name.lower() for s in job.required_skills.all()}
            if not job_skills:
                continue
            already_applied = set(
                Application.objects.filter(job=job).values_list('student_id', flat=True)
            )
            candidates = (
                Student.objects
                .exclude(id__in=already_applied)
                .order_by('-trust_score')[:50]
            )
            best_matches = []
            for student in candidates:
                s_skills = student_skill_map.get(str(student.id), set())
                overlap = s_skills & job_skills
                if not overlap:
                    continue
                score = round(len(overlap) / len(job_skills) * 100, 1)
                if score >= 30:
                    best_matches.append({
                        'student_id': str(student.id),
                        'name': student.name,
                        'department': student.department or '',
                        'match_score': score,
                        'trust_score': round(float(student.trust_score or 0), 1),
                    })
            best_matches.sort(key=lambda x: x['match_score'], reverse=True)
            top_candidates.append({
                'job_id': str(job.id),
                'job_title': job.title,
                'recommended_candidates': best_matches[:5]
            })

        return JsonResponse({
            'status': 'success',
            'company_name': company.name,
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
            
            if deadline and django_timezone.is_naive(deadline):
                deadline = django_timezone.make_aware(deadline)
            job = Job.objects.create(
                company=company,
                title=data['title'],
                description=data['description'],
                min_cgpa=data.get('min_cgpa'),
                job_type=data.get('job_type'),
                salary_range=data.get('salary_range', {}),
                location=data.get('location') or '',
                deadline=deadline,
                department_category=data.get('department_category', 'any'),
            )
            
            for skill_name in data.get('required_skills', []):
                skill_name_clean = skill_name.strip().lower()
                skill, _ = Skill.objects.get_or_create(
                    name=skill_name_clean,
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
            
        except Exception as e:
            import traceback
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
        
        applications = Application.objects.filter(job_id=job_id).select_related('student', 'job', 'scheduled_interview')
        data = []
        for app in applications:
            # Latest agent run for this application
            latest_run = app.agent_runs.filter(status='completed').first()
            # AI Interview data (safe lookup — no walrus operator)
            ai_iv = app.ai_interviews.order_by('-created_at').first()
            booking = getattr(app, 'scheduled_interview', None)
            data.append({
                'id': str(app.id),
                'student_id': str(app.student.id),
                'student_name': app.student.name,
                'job_id': str(app.job.id),
                'job_title': app.job.title,
                'match_score': float(app.match_score) if app.match_score else 0,
                'status': app.status,
                'applied_at': app.applied_at.isoformat(),
                # Agent data
                'agent_decision': latest_run.decision if latest_run else None,
                'agent_score':    round(latest_run.score * 100, 1) if latest_run else None,
                'agent_confidence': latest_run.confidence if latest_run else None,
                'agent_run_url': f'/company/agent-run/{latest_run.id}/' if latest_run else None,
                'agent_run_id':  str(latest_run.id) if latest_run else None,
                'agent_run_count': app.agent_runs.count(),
                # AI Interview data
                'ai_interview_id':         str(ai_iv.id) if ai_iv else None,
                'ai_interview_status':     ai_iv.status if ai_iv else None,
                'ai_interview_result_url': f'/company/interview/{ai_iv.id}/result/' if ai_iv else None,
                'can_schedule_interview': app.status in ('shortlisted', 'interview') and (
                    booking is None or booking.status == 'cancelled'
                ),
                'scheduled_interview': {
                    'id': str(booking.id),
                    'status': booking.status,
                    'date': booking.date.isoformat(),
                    'start_time': booking.start_time.strftime('%H:%M'),
                    'end_time': booking.end_time.strftime('%H:%M'),
                    'meeting_type': booking.meeting_type,
                } if booking else None,
            })
        return JsonResponse({'status': 'success', 'applications': data})
@method_decorator(csrf_exempt, name='dispatch')
class UpdateApplicationView(View):

    def post(self, request):
        """Update application status (shortlist, reject, etc.)"""
        data = json.loads(request.body)
        application = get_object_or_404(Application, id=data['application_id'])

        old_status = application.status
        new_status = data['status']
        if old_status == new_status:
            return JsonResponse({'status': 'success', 'message': 'Application status already updated'})
        application.status = new_status
        application.save()

        # ── RL signal: shortlisted → rejected  ────────────────────────────
        if old_status == 'shortlisted' and new_status == 'rejected':
            try:
                engine = AIMatchingEngine(application.job.company)
                engine.update_weights_from_feedback(
                    application.job.company, application, trigger='reject'
                )
            except Exception as e:
                pass  # Profile and provider content must not be logged.

        # Create notification for student
        Notification.objects.create(
            user_id=application.student.id,
            user_type='student',
            type=f'status_{new_status}',
            title=f'Application {new_status.title()}',
            message=f'Your application for {application.job.title} has been {new_status}',
            data={'job_id': str(application.job.id)}
        )

        return JsonResponse({
            'status': 'success',
            'message': f'Application status updated to {new_status}'
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
            
            # In-app notification
            Notification.objects.create(
                user_id=app.student.id,
                user_type='student',
                type='shortlisted',
                title=f'Congratulations! Shortlisted for {job.title}',
                message=f'You have been shortlisted by {job.company.name} based on your match score of {app.match_score:.1f}%',
                data={'job_id': str(job.id)}
            )
            # Email + points
            try:
                from .utils.email_helpers import send_shortlist_email
                from .utils.points import award_points
                send_shortlist_email(app)
                award_points(app.student, 'shortlisted', unique_key=str(app.id))
            except Exception:
                pass

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
        if previous_status == 'hired':
            return JsonResponse({'status': 'success', 'message': 'Candidate already hired', 'ai_adjusted': False})
        application.status = 'hired'
        application.save()
        
        # Trigger RL weight agent (hire = +1 reward)
        engine = AIMatchingEngine(application.job.company)
        new_weights = engine.update_weights_from_feedback(
            application.job.company, application, trigger='hire'
        )

        # Email + points
        try:
            from .utils.email_helpers import send_hired_email
            from .utils.points import award_points
            send_hired_email(application)
            award_points(application.student, 'hired', unique_key=str(application.id))
        except Exception:
            pass

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
        from django.utils import timezone as _tz
        notifications = Notification.objects.filter(
            user_id=user_id,
            user_type=user_type
        ).order_by('-created_at')

        def _time_ago(dt):
            diff = _tz.now() - dt
            s = int(diff.total_seconds())
            if s < 60: return 'just now'
            if s < 3600: return f'{s//60}m ago'
            if s < 86400: return f'{s//3600}h ago'
            return f'{s//86400}d ago'

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
                    'time_ago': _time_ago(n.created_at),
                    'created_at': n.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
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
class MarkAllNotificationsReadView(View):
    """Mark every unread notification for a student/company as read."""
    def post(self, request, user_id):
        Notification.objects.filter(user_id=user_id, read=False).update(read=True)
        return JsonResponse({'status': 'success'})


class InterviewSlotAvailabilityView(View):
    """Get detailed slot availability for company"""
    
    def get(self, request, job_id):
        from core.models import InterviewSlot, ScheduledInterview  # Local imports
        
        try:
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            slots = InterviewSlot.objects.filter(
                job=job, is_active=True, date__gte=django_timezone.localdate()
            ).order_by('date', 'start_time')
            
            slot_data = []
            for slot in slots:
                generated_slots = slot.generate_time_slots()
                
                # Get booked interviews for this slot
                booked = ScheduledInterview.objects.filter(
                    application__job=job, date=slot.date,
                    start_time__lt=slot.end_time, end_time__gt=slot.start_time,
                ).exclude(status='cancelled').select_related('application__student')
                
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
        request.session.flush()
        return JsonResponse({'status': 'success'})

@method_decorator(csrf_exempt, name='dispatch')
class CompanyLogoutView(View):
    def post(self, request):
        request.session.flush()
        return JsonResponse({'status': 'success'})
    
@method_decorator(csrf_exempt, name='dispatch')
class AddSkillView(View):
    def post(self, request, student_id):
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=student_id)
        
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
    def post(self, request, student_id):
        data = json.loads(request.body)
        student = get_object_or_404(Student, id=student_id)
        
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
class ApplicationStatusDetailView(View):
    """Return full status details for a student's application to a specific job."""

    def get(self, request, student_id, job_id):
        from django.utils import timezone as _tz

        student = get_object_or_404(Student, id=student_id)
        job     = get_object_or_404(Job, id=job_id)

        application = Application.objects.filter(student=student, job=job).first()
        if not application:
            return JsonResponse({'status': 'not_applied'}, status=404)

        # Scheduled interview
        scheduled = None
        try:
            si = application.scheduled_interview
            scheduled = {
                'date':         si.date.strftime('%B %d, %Y') if si.date else None,
                'time':         si.start_time.strftime('%I:%M %p') if si.start_time else None,
                'location':     si.location or '',
                'contact':      si.contact_person or '',
                'meeting_link': si.meeting_link or '',
            }
        except Exception:
            pass

        # AI Interview
        ai_interview = None
        ai_iv = application.ai_interviews.order_by('-created_at').first()
        if ai_iv:
            ai_interview = {
                'status':          ai_iv.status,
                'score':           round(ai_iv.interview_score, 1) if ai_iv.interview_score else None,
                'combined_score':  round(ai_iv.combined_score, 1)  if ai_iv.combined_score  else None,
                'expires_at':      ai_iv.expires_at.strftime('%B %d, %Y at %I:%M %p') if ai_iv.expires_at else None,
                'interview_url':   f'/interview/{ai_iv.token}/' if ai_iv.status in ('pending','in_progress') else None,
                'result_url':      f'/company/interview/{ai_iv.id}/result/' if ai_iv.status == 'completed' else None,
            }

        # Recruitment agent latest decision
        agent_decision = None
        latest_run = application.agent_runs.order_by('-created_at').first()
        if latest_run:
            agent_decision = {
                'decision':   latest_run.decision,
                'score':      round(latest_run.score * 100, 1),
                'confidence': latest_run.confidence,
            }

        def _time_ago(dt):
            diff = _tz.now() - dt
            s = int(diff.total_seconds())
            if s < 60: return 'just now'
            if s < 3600: return f'{s//60}m ago'
            if s < 86400: return f'{s//3600}h ago'
            return f'{s//86400}d ago'

        return JsonResponse({
            'status': 'ok',
            'application': {
                'id':           str(application.id),
                'status':       application.status,
                'match_score':  round(float(application.match_score or 0), 1),
                'applied_at':   application.applied_at.strftime('%B %d, %Y'),
                'applied_ago':  _time_ago(application.applied_at),
                'job_title':    job.title,
                'company_name': job.company.name,
            },
            'scheduled_interview': scheduled,
            'ai_interview':        ai_interview,
            'agent_decision':      agent_decision,
        })


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
        
class StudentAIInterviewsView(View):
    """Return all pending/in-progress AI interviews for a student."""
    def get(self, request, student_id):
        student = get_object_or_404(Student, id=student_id)
        try:
            interviews = AIInterview.objects.filter(
                application__student=student,
                status__in=['pending', 'in_progress'],
            ).select_related('application__job__company').order_by('-created_at')

            from django.utils import timezone as tz
            data = []
            for iv in interviews:
                job     = iv.application.job
                is_exp  = iv.expires_at and tz.now() > iv.expires_at
                if is_exp:
                    continue  # skip expired
                site_url      = getattr(__import__('django').conf.settings, 'SITE_URL', 'http://127.0.0.1:8000')
                interview_url = f'{site_url}/interview/{iv.token}/'
                data.append({
                    'interview_id':   str(iv.id),
                    'token':          iv.token,
                    'interview_url':  interview_url,
                    'status':         iv.status,
                    'job_title':      job.title,
                    'company_name':   job.company.name,
                    'deadline':       iv.expires_at.strftime('%B %d, %Y at %I:%M %p') if iv.expires_at else None,
                    'expires_at':     iv.expires_at.strftime('%Y-%m-%dT%H:%M:%SZ') if iv.expires_at else None,
                    'questions_total': len(iv.questions) if iv.questions else 0,
                    'answers_given':  len(iv.answers) if iv.answers else 0,
                    'created_at':     iv.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
        except Exception as e:
            # If migration hasn't been run yet, return empty list gracefully
            data = []

        return JsonResponse({'status': 'success', 'interviews': data})


@method_decorator(csrf_exempt, name='dispatch')
class CareerAdvisorChatView(View):
    """Gemini-powered career advisor chatbot for students."""

    def post(self, request, student_id):
        pass  # genai import removed — using llm_client centrally
        import json as _json
        from core.models import AdvisorSession, AdvisorMessage
        student = get_object_or_404(Student, id=student_id)
        try:
            body = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        user_message = body.get('message', '').strip()
        session_id   = body.get('session_id')
        history      = body.get('history', [])   # [{role, content}]
        if not user_message:
            return JsonResponse({'status': 'error', 'message': 'Empty message'}, status=400)

        # Resolve or create session
        session = None
        if session_id:
            try:
                session = AdvisorSession.objects.get(id=session_id, student=student)
            except AdvisorSession.DoesNotExist:
                pass
        if not session:
            session = AdvisorSession.objects.create(student=student, title=user_message[:80])

        # Build history from DB for this session (more reliable than client-sent)
        db_messages = list(session.messages.values('role', 'content').order_by('-created_at')[:12])[::-1]
        history = db_messages  # use DB history, ignore client-sent history

        # Build student context
        skills = [ss.skill.name for ss in StudentSkill.objects.filter(student=student).select_related('skill')]
        experiences = [
            f"{e.role} at {e.company_name}"
            for e in student.experiences.all()
        ]
        applied_titles = list(
            Application.objects.filter(student=student)
            .select_related('job').values_list('job__title', flat=True)[:10]
        )
        context = f"""You are a sharp, practical AI Career Advisor. Your job is to give this specific student direct, actionable advice — not generic tips.

STUDENT PROFILE:
- Name: {student.name}
- Department: {student.department or 'Not specified'}
- CGPA: {student.cgpa or 'Not specified'}
- Skills: {', '.join(skills) if skills else 'None listed'}
- Experience: {'; '.join(experiences) if experiences else 'No experience yet'}
- Jobs Applied To: {', '.join(applied_titles) if applied_titles else 'None yet'}
- Trust Score: {student.trust_score or 0:.0f}/100
- Projects: {student.projects.count()} projects

STRICT OUTPUT RULES:
- Max 180 words total
- When listing items, use "- Item" format (dash + space), one per line
- Use **bold** only for section labels or key terms (e.g. **Next step:**)
- Do NOT use asterisks (*) as bullet points — use dash (-) only
- Start with the direct answer, not pleasantries
- Refer to the student by name at most once
- Be specific to their actual profile above, not generic advice
- NEVER use placeholder variables like X%, Y%, [value], <number>, or "e.g., ..." style templates in your response — only give concrete, real advice
- NEVER say "quantify your impact with X%" or similar — if you can't give a specific number, don't mention numbers at all"""

        # Build conversation for Gemini
        conv_parts = [context, "\n\nCONVERSATION:"]
        for h in history[-6:]:   # last 6 turns max
            role = "Student" if h.get('role') == 'user' else "Advisor"
            conv_parts.append(f"{role}: {h.get('content','')}")
        conv_parts.append(f"Student: {user_message}")
        conv_parts.append("Advisor:")

        import logging as _logging
        _log = _logging.getLogger(__name__)
        from core.utils.llm_client import llm_generate as _llm_generate

        _prompt = '\n'.join(conv_parts)
        reply = None
        _last_error = None

        try:
            _log.warning("[CareerAdvisor] Calling llm_generate (Gemini → Ollama fallback)")
            reply = _llm_generate(_prompt).strip()
            _log.warning("[CareerAdvisor] SUCCESS")
        except Exception as e:
            _last_error = str(e)
            _log.error(f"[CareerAdvisor] ALL backends failed: {_last_error}")

        if not reply:
            reply = "⚠️ AI service is temporarily unavailable (Gemini + local model both failed). Please try again in a moment."
            return JsonResponse({
                'status': 'error',
                'reply': reply,
                'session_id': str(session.id) if session else None,
                'session_title': session.title if session else None,
            })

        # Save messages to DB
        AdvisorMessage.objects.create(session=session, role='user', content=user_message)
        AdvisorMessage.objects.create(session=session, role='assistant', content=reply)
        # Touch updated_at
        session.save(update_fields=['updated_at'])

        return JsonResponse({
            'status': 'success',
            'reply': reply,
            'session_id': str(session.id),
            'session_title': session.title,
        })


@method_decorator(csrf_exempt, name='dispatch')
class AdvisorSessionListView(View):
    """List all sessions for a student (GET) or delete one (DELETE)."""

    def get(self, request, student_id):
        from core.models import AdvisorSession
        student = get_object_or_404(Student, id=student_id)
        sessions = AdvisorSession.objects.filter(student=student).order_by('-updated_at')[:50]
        return JsonResponse({'sessions': [
            {
                'id': str(s.id),
                'title': s.title,
                'updated_at': s.updated_at.isoformat(),
            }
            for s in sessions
        ]})

    def delete(self, request, student_id):
        import json as _json
        from core.models import AdvisorSession
        student = get_object_or_404(Student, id=student_id)
        try:
            body = _json.loads(request.body)
            session_id = body.get('session_id')
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        AdvisorSession.objects.filter(id=session_id, student=student).delete()
        return JsonResponse({'status': 'ok'})


@method_decorator(csrf_exempt, name='dispatch')
class AdvisorSessionDetailView(View):
    """Return all messages for a session."""

    def get(self, request, student_id, session_id):
        from core.models import AdvisorSession, AdvisorMessage
        student = get_object_or_404(Student, id=student_id)
        session = get_object_or_404(AdvisorSession, id=session_id, student=student)
        messages = session.messages.order_by('created_at')
        return JsonResponse({
            'session_id': str(session.id),
            'title': session.title,
            'messages': [
                {'role': m.role, 'content': m.content}
                for m in messages
            ]
        })


# ──────────────────────────────────────────────────────────────────
# AUTO HIRING PIPELINE VIEWS
# ──────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class PipelineCreateView(View):
    """Create and start a new pipeline for a job."""
    def post(self, request, job_id):
        import json as _json
        from core.models import PipelineRun, PipelineCandidate
        from core.utils.pipeline_engine import run_sort

        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        job = get_object_or_404(Job, id=job_id)
        if str(job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        try:
            body = _json.loads(request.body)
        except Exception:
            body = {}

        company = get_object_or_404(Company, id=company_id)

        # Cancel any existing active pipeline for this job
        PipelineRun.objects.filter(job=job).exclude(stage__in=['completed', 'cancelled']).update(stage='cancelled')

        pipeline = PipelineRun.objects.create(
            job=job,
            created_by=company,
            sort_top_n=int(body.get('sort_top_n', 20)),
            vetting_top_n=int(body.get('vetting_top_n', 10)),
            interview_top_n=int(body.get('interview_top_n', 5)),
        )

        count = run_sort(pipeline)

        return JsonResponse({
            'status': 'success',
            'pipeline_id': str(pipeline.id),
            'candidates_scored': count,
            'message': f'Pipeline started. {count} candidates scored.',
        })




@method_decorator(csrf_exempt, name='dispatch')
class PipelineApproveSortView(View):
    """Company approves sorted list -> vetting tests sent."""
    def post(self, request, pipeline_id):
        import json as _json
        from core.models import PipelineRun
        from core.utils.pipeline_engine import approve_sort_and_send_vetting
        from django.utils.dateparse import parse_datetime

        company_id = request.session.get('company_id')
        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        try:
            body = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        approved_ids = body.get('approved_application_ids', [])
        deadline_str = body.get('vetting_deadline')
        if not approved_ids or not deadline_str:
            return JsonResponse({'status': 'error', 'message': 'approved_application_ids and vetting_deadline required'}, status=400)

        from django.utils import timezone as _tz
        try:
            deadline = parse_datetime(deadline_str)
            if deadline and not deadline.tzinfo:
                import pytz
                deadline = pytz.utc.localize(deadline)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid deadline format'}, status=400)

        if not deadline or deadline <= _tz.now():
            return JsonResponse({'status': 'error', 'message': 'Deadline must be in the future'}, status=400)

        approve_sort_and_send_vetting(pipeline, approved_ids, deadline)
        return JsonResponse({'status': 'success', 'message': f'{len(approved_ids)} candidates sent vetting test.'})


@method_decorator(csrf_exempt, name='dispatch')
class PipelineApproveVettingView(View):
    """Company approves vetting results -> AI interviews sent."""
    def post(self, request, pipeline_id):
        import json as _json
        from core.models import PipelineRun
        from core.utils.pipeline_engine import approve_vetting_and_send_interviews
        from django.utils.dateparse import parse_datetime

        company_id = request.session.get('company_id')
        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        try:
            body = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        approved_ids = body.get('approved_application_ids', [])
        deadline_str = body.get('interview_deadline')
        if not approved_ids or not deadline_str:
            return JsonResponse({'status': 'error', 'message': 'approved_application_ids and interview_deadline required'}, status=400)

        from django.utils import timezone as _tz
        try:
            deadline = parse_datetime(deadline_str)
            if deadline and not deadline.tzinfo:
                import pytz
                deadline = pytz.utc.localize(deadline)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid deadline format'}, status=400)

        if not deadline or deadline <= _tz.now():
            return JsonResponse({'status': 'error', 'message': 'Deadline must be in the future'}, status=400)

        approve_vetting_and_send_interviews(pipeline, approved_ids, deadline)
        return JsonResponse({'status': 'success', 'message': f'{len(approved_ids)} candidates sent AI interview.'})


@method_decorator(csrf_exempt, name='dispatch')
class PipelineCancelView(View):
    """Cancel a running pipeline."""
    def post(self, request, pipeline_id):
        from core.models import PipelineRun
        company_id = request.session.get('company_id')
        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        pipeline.stage = 'cancelled'
        pipeline.save(update_fields=['stage', 'updated_at'])
        return JsonResponse({'status': 'success'})


@method_decorator(csrf_exempt, name='dispatch')
class JobPipelineListView(View):
    """List all pipelines for a job."""
    def get(self, request, job_id):
        from core.models import PipelineRun
        company_id = request.session.get('company_id')
        job = get_object_or_404(Job, id=job_id)
        if str(job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        pipelines = PipelineRun.objects.filter(job=job).order_by('-created_at')[:5]
        return JsonResponse({'pipelines': [
            {
                'id': str(p.id),
                'stage': p.stage,
                'stage_label': p.get_stage_display(),
                'created_at': p.created_at.isoformat(),
                'total_candidates': p.candidates.count(),
                'final_candidates': p.candidates.filter(stage='final').count(),
            }
            for p in pipelines
        ]})




@method_decorator(csrf_exempt, name='dispatch')
class ReportInterviewCheatingView(View):
    """Student's browser reports a cheating violation during AI interview."""

    def post(self, request, token):
        import json as _json
        interview = get_object_or_404(AIInterview, token=token)

        # Security: must be the right student
        student_id = request.session.get('student_id')
        if not student_id or str(interview.application.student.id) != str(student_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        try:
            data = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        log = interview.cheating_log or {
            'tab_switches': 0, 'fullscreen_exits': 0,
            'copy_pastes': 0, 'violations': [], 'auto_submitted': False
        }
        violation_type = data.get('type', 'unknown')
        log['violations'].append({
            'type': violation_type,
            'at': data.get('at', ''),
            'count': data.get('count', 1),
        })
        if violation_type == 'tab_switch':
            log['tab_switches'] = log.get('tab_switches', 0) + 1
        elif violation_type == 'fullscreen_exit':
            log['fullscreen_exits'] = log.get('fullscreen_exits', 0) + 1
        elif violation_type == 'copy_paste':
            log['copy_pastes'] = log.get('copy_pastes', 0) + 1

        auto_submit = data.get('auto_submit', False)
        if auto_submit:
            log['auto_submitted'] = True

        interview.cheating_log = log
        interview.save(update_fields=['cheating_log'])

        # Notify company if cheating flagged
        total_violations = log.get('tab_switches', 0) + log.get('fullscreen_exits', 0) + log.get('copy_pastes', 0)
        if total_violations >= 3 or auto_submit:
            student = interview.application.student
            company = interview.application.job.company
            Notification.objects.create(
                user_id=company.id,
                user_type='company',
                type='warning',
                title='⚠️ Cheating Detected — AI Interview',
                message=(
                    f"{student.name} triggered {total_violations} violations "
                    f"(tab switches: {log.get('tab_switches',0)}, "
                    f"fullscreen exits: {log.get('fullscreen_exits',0)}, "
                    f"copy-paste: {log.get('copy_pastes',0)}) "
                    f"during their AI interview for {interview.application.job.title}."
                ),
                data={
                    'interview_id': str(interview.id),
                    'student_name': student.name,
                    'job_title': interview.application.job.title,
                    'cheating_log': log,
                }
            )

        return JsonResponse({'status': 'success', 'total_violations': total_violations})


def _build_heatmap_response():
    """
    Build the skill-demand heatmap payload using aggregated DB queries.
    Replaces the old N+1 per-job loop approach — typically 5-10x faster.
    """
    from django.db.models import Count, Value
    from django.db.models.functions import Lower, Coalesce
    from datetime import timedelta
    from django.utils import timezone as tz

    week_ago = tz.now() - timedelta(days=7)

    # --- 1. Skill demand across ALL active jobs (single query) ---
    skill_demand_rows = (
        Job.objects.filter(status='active', required_skills__name__isnull=False)
        .values('required_skills__name')
        .annotate(count=Count('id', distinct=True))
        .order_by('-count')
    )
    skill_demand = {row['required_skills__name'].lower(): row['count'] for row in skill_demand_rows}

    # --- 2. Student supply per skill (single query) ---
    student_rows = (
        StudentSkill.objects.filter(skill__name__isnull=False)
        .values('skill__name')
        .annotate(count=Count('id'))
    )
    student_skill_counts = {row['skill__name'].lower(): row['count'] for row in student_rows}

    # --- 3. Department breakdown (single query) ---
    dept_rows = (
        Job.objects.filter(status='active', required_skills__name__isnull=False)
        .values('department_category', 'required_skills__name')
        .annotate(count=Count('id', distinct=True))
    )
    dept_skills = {}
    for row in dept_rows:
        dept = row['department_category'] or 'General'
        skill = row['required_skills__name']
        if dept not in dept_skills:
            dept_skills[dept] = {}
        dept_skills[dept][skill] = dept_skills[dept].get(skill, 0) + row['count']

    # --- 4. Weekly trend (single query) ---
    weekly_rows = (
        Job.objects.filter(status='active', created_at__gte=week_ago, required_skills__name__isnull=False)
        .values('required_skills__name')
        .annotate(count=Count('id', distinct=True))
        .order_by('-count')[:10]
    )
    weekly_top = [(row['required_skills__name'], row['count']) for row in weekly_rows]

    # --- Build top10 + gap ---
    top10 = sorted(skill_demand.items(), key=lambda x: x[1], reverse=True)[:10]

    gap_data = [
        {
            'skill': skill_name.title(),
            'demand': demand_count,
            'supply': student_skill_counts.get(skill_name, 0),
            'gap': max(0, demand_count - student_skill_counts.get(skill_name, 0)),
        }
        for skill_name, demand_count in top10
    ]

    dept_breakdown = {
        dept: [{'skill': s, 'count': c} for s, c in sorted(skills.items(), key=lambda x: x[1], reverse=True)[:5]]
        for dept, skills in dept_skills.items()
    }

    total_jobs    = Job.objects.filter(status='active').count()
    total_students = Student.objects.count()

    return JsonResponse({
        'status': 'success',
        'top10': [{'skill': s.title(), 'count': c} for s, c in top10],
        'gap_data': gap_data,
        'dept_breakdown': dept_breakdown,
        'weekly_trend': [{'skill': s.title(), 'count': c} for s, c in weekly_top],
        'total_active_jobs': total_jobs,
        'total_students': total_students,
    })


@method_decorator(csrf_exempt, name='dispatch')
class SkillDemandHeatmapView(View):
    """Returns skill demand analytics for company dashboard heatmap."""

    def get(self, request, company_id):
        company = get_object_or_404(Company, id=company_id)
        return _build_heatmap_response()


@method_decorator(csrf_exempt, name='dispatch')
class PlatformSkillHeatmapView(View):
    """Platform-wide skill demand heatmap — no company filter, accessible to students."""

    def get(self, request):
        return _build_heatmap_response()


# ─────────────────────────────────────────────────────────────────────────────
# AUTO PIPELINE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class CreatePipelineView(View):
    """Start an auto pipeline for a job. Runs sort immediately."""

    def post(self, request):
        import json as _json
        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        try:
            body = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        job_id      = body.get('job_id')
        sort_top_n  = int(body.get('sort_top_n', 20))
        vet_top_n   = int(body.get('vetting_top_n', 10))
        int_top_n   = int(body.get('interview_top_n', 5))

        job = get_object_or_404(Job, id=job_id)
        if str(job.company.id) != company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        from core.models import PipelineRun, Company
        from core.utils.pipeline_engine import run_sort

        company = get_object_or_404(Company, id=company_id)

        # Cancel any existing active pipeline for this job
        PipelineRun.objects.filter(
            job=job
        ).exclude(stage__in=['completed', 'cancelled']).update(stage='cancelled')

        pipeline = PipelineRun.objects.create(
            job=job,
            created_by=company,
            sort_top_n=sort_top_n,
            vetting_top_n=vet_top_n,
            interview_top_n=int_top_n,
        )

        count = run_sort(pipeline)
        return JsonResponse({
            'status': 'ok',
            'pipeline_id': str(pipeline.id),
            'total_sorted': count,
            'message': f'Pipeline started. {count} candidates sorted.',
        })


@method_decorator(csrf_exempt, name='dispatch')
class PipelineStatusView(View):
    """Get full pipeline status + candidates. Also auto-advances on deadlines."""

    def get(self, request, pipeline_id):
        company_id = request.session.get('company_id')
        from core.models import PipelineRun
        from core.utils.pipeline_engine import check_and_advance_deadlines, get_pipeline_report

        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        # Auto-advance if deadlines passed
        check_and_advance_deadlines(pipeline)
        pipeline.refresh_from_db()

        report = get_pipeline_report(pipeline)

        # Add deadline info
        report['sort_top_n']     = pipeline.sort_top_n
        report['vetting_top_n']  = pipeline.vetting_top_n
        report['interview_top_n']= pipeline.interview_top_n
        report['vetting_deadline']  = pipeline.vetting_deadline.isoformat() if pipeline.vetting_deadline else None
        report['interview_deadline']= pipeline.interview_deadline.isoformat() if pipeline.interview_deadline else None
        report['job_id']         = str(pipeline.job.id)
        report['created_at']     = pipeline.created_at.isoformat()

        return JsonResponse({'status': 'ok', **report})


@method_decorator(csrf_exempt, name='dispatch')
class ApproveSortView(View):
    """Company approves sorted list → generate vetting test → send to candidates."""

    def post(self, request, pipeline_id):
        import json as _json
        from django.utils.dateparse import parse_datetime
        company_id = request.session.get('company_id')
        from core.models import PipelineRun
        from core.utils.pipeline_engine import approve_sort_and_send_vetting

        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        if pipeline.stage != 'sort_review':
            return JsonResponse({'status': 'error', 'message': f'Pipeline is in stage: {pipeline.stage}'}, status=400)

        try:
            body = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        approved_ids      = body.get('approved_application_ids', [])
        vetting_deadline  = parse_datetime(body.get('vetting_deadline', ''))
        # Assessment configuration fields (optional — improve question quality)
        assessment_topic    = body.get('assessment_topic', '').strip()
        assessment_type     = body.get('assessment_type', '').strip()   # 'coding' | 'mcq_written' | ''
        assessment_keywords = body.get('assessment_keywords', '').strip()

        if not approved_ids or not vetting_deadline:
            return JsonResponse({'status': 'error', 'message': 'approved_application_ids and vetting_deadline required'}, status=400)

        from django.utils import timezone as _tz
        if not _tz.is_aware(vetting_deadline):
            vetting_deadline = _tz.make_aware(vetting_deadline)

        try:
            approve_sort_and_send_vetting(
                pipeline, approved_ids, vetting_deadline,
                topic=assessment_topic,
                force_type=assessment_type,
                keywords=assessment_keywords,
            )
        except RuntimeError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=503)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        return JsonResponse({'status': 'ok', 'message': f'Vetting tests sent to {len(approved_ids)} candidates.'})


@method_decorator(csrf_exempt, name='dispatch')
class ApproveVettingView(View):
    """Company approves vetting results → send AI interviews."""

    def post(self, request, pipeline_id):
        import json as _json
        from django.utils.dateparse import parse_datetime
        company_id = request.session.get('company_id')
        from core.models import PipelineRun
        from core.utils.pipeline_engine import approve_vetting_and_send_interviews

        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        if pipeline.stage != 'vetting_review':
            return JsonResponse({'status': 'error', 'message': f'Pipeline is in stage: {pipeline.stage}'}, status=400)

        try:
            body = _json.loads(request.body)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        approved_ids        = body.get('approved_application_ids', [])
        interview_deadline  = parse_datetime(body.get('interview_deadline', ''))
        if not approved_ids or not interview_deadline:
            return JsonResponse({'status': 'error', 'message': 'approved_application_ids and interview_deadline required'}, status=400)

        from django.utils import timezone as _tz
        if not _tz.is_aware(interview_deadline):
            interview_deadline = _tz.make_aware(interview_deadline)

        try:
            approve_vetting_and_send_interviews(pipeline, approved_ids, interview_deadline)
        except RuntimeError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=503)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        return JsonResponse({'status': 'ok', 'message': f'AI interviews sent to {len(approved_ids)} candidates.'})


@method_decorator(csrf_exempt, name='dispatch')
class CancelPipelineView(View):
    """Cancel an active pipeline."""

    def post(self, request, pipeline_id):
        company_id = request.session.get('company_id')
        from core.models import PipelineRun
        pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
        if str(pipeline.job.company.id) != company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        pipeline.stage = 'cancelled'
        pipeline.save(update_fields=['stage', 'updated_at'])
        return JsonResponse({'status': 'ok', 'message': 'Pipeline cancelled.'})


@method_decorator(csrf_exempt, name='dispatch')
class JobPipelinesView(View):
    """List all pipelines for a job."""

    def get(self, request, job_id):
        company_id = request.session.get('company_id')
        from core.models import PipelineRun
        job = get_object_or_404(Job, id=job_id, company__id=company_id)
        pipelines = PipelineRun.objects.filter(job=job).order_by('-created_at')
        return JsonResponse({'status': 'ok', 'pipelines': [
            {
                'id': str(p.id),
                'stage': p.stage,
                'sort_top_n': p.sort_top_n,
                'vetting_top_n': p.vetting_top_n,
                'interview_top_n': p.interview_top_n,
                'created_at': p.created_at.isoformat(),
                'total_candidates': p.candidates.count(),
            }
            for p in pipelines
        ]})


# Page view for pipeline
def company_pipeline_page(request, pipeline_id):
    company_id = request.session.get('company_id')
    if not company_id:
        return redirect('/company/login/')
    from core.models import PipelineRun
    pipeline = get_object_or_404(PipelineRun, id=pipeline_id)
    if str(pipeline.job.company.id) != company_id:
        from django.http import Http404
        raise Http404
    return render(request, 'company/pipeline.html', {
        'pipeline_id': str(pipeline_id),
        'job_title': pipeline.job.title,
        'job_id': str(pipeline.job.id),
        'company_id': company_id,
    })


def student_career_advisor_page(request):
    """Render the full-page Career Advisor chatbot."""
    student_id = request.session.get('student_id')
    if not student_id:
        return redirect(f'/student/login/?next=/student/career-advisor/')
    try:
        _student = Student.objects.get(id=student_id)
        _name = _student.name
    except Student.DoesNotExist:
        _name = 'Student'
    return render(request, 'student/career_advisor.html', {
        'student_id': student_id,
        'student_name': _name,
    })


@method_decorator(csrf_exempt, name='dispatch')
class UploadResumeView(View):
    def post(self, request, student_id):
        try:
            student = get_object_or_404(Student, id=student_id)
            
            uploaded_file = request.FILES.get('resume')
            if not uploaded_file:
                return JsonResponse({'status': 'error', 'message': 'No resume file provided'}, status=400)
            
            
            # Parse resume first before Django consumes the file stream
            parser = ResumeParser()
            parsed_data = parser.parse_resume(uploaded_file)
            if parsed_data.get('parse_status') == 'failed':
                return JsonResponse({'status': 'error', 'message': parsed_data['error']}, status=422)
            
            
            # Reset pointer and save to model
            uploaded_file.seek(0)
            student.resume = uploaded_file
            student.save()
            
            # Run fraud detection with parsed CGPA
            try:
                fraud_engine = FraudDetectionEngine()
                fraud_engine.analyze_student(student, cv_cgpa=parsed_data.get('cgpa'))
            except Exception as fraud_err:
                pass  # Profile and provider content must not be logged.
            
            return JsonResponse({
                'status': 'success',
                'data': parsed_data
            })
            
        except Exception as e:
            import traceback
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        
# ==================== LINKEDIN PDF UPLOAD VIEW ====================

class LinkedInPDFUploadView(View):
    """
    POST /api/student/<student_id>/upload-linkedin/
    Accepts a LinkedIn PDF export, parses it with Gemini, cross-validates against
    existing profile skills, updates linkedin_score, and returns the diff.
    """
    def post(self, request, student_id):
        try:
            from .utils.linkedin_parser import LinkedInParser, calculate_linkedin_score

            student = get_object_or_404(Student, id=student_id)
            uploaded_file = request.FILES.get('linkedin_pdf')
            if not uploaded_file:
                return JsonResponse({'status': 'error', 'message': 'No LinkedIn PDF provided'}, status=400)


            # 1. Parse the LinkedIn PDF
            parser = LinkedInParser()
            parsed = parser.parse(uploaded_file)
            if parsed.get('parse_status') == 'failed':
                return JsonResponse({'status': 'error', 'message': parsed['error']}, status=422)

            # 2. Cross-validate skills against existing CV/manual skills
            existing_skills = StudentSkill.objects.filter(student=student).select_related('skill')
            existing_by_name = {ss.skill.name.lower(): ss for ss in existing_skills}

            cross_validated_count = 0
            linkedin_only_skills = []
            newly_cross_validated = []

            for li_skill in parsed.get('skills', []):
                name_lower = li_skill['name'].lower()
                if name_lower in existing_by_name:
                    # Skill exists in both CV and LinkedIn → mark cross-validated
                    ss = existing_by_name[name_lower]
                    if not ss.cross_validated:
                        ss.cross_validated = True
                        # Promote proficiency if LinkedIn suggests higher
                        level_order = {'Beginner': 0, 'Intermediate': 1, 'Expert': 2}
                        if level_order.get(li_skill.get('level', 'Beginner'), 0) > level_order.get(ss.proficiency_level, 0):
                            ss.proficiency_level = li_skill['level']
                        ss.save()
                        newly_cross_validated.append(li_skill['name'])
                    cross_validated_count += 1
                else:
                    # LinkedIn-only skill — add to profile
                    linkedin_only_skills.append(li_skill)

            # Add LinkedIn-only skills to the student's profile
            added_skills = []
            for li_skill in linkedin_only_skills:
                try:
                    skill_obj, _ = Skill.objects.get_or_create(
                        name__iexact=li_skill['name'],
                        defaults={
                            'name': li_skill['name'],
                            'category': li_skill.get('category', 'Uncategorized'),
                        }
                    )
                    StudentSkill.objects.get_or_create(
                        student=student,
                        skill=skill_obj,
                        defaults={
                            'proficiency_level': li_skill.get('level', 'Intermediate'),
                            'source': 'linkedin',
                            'cross_validated': False,
                        }
                    )
                    added_skills.append(li_skill['name'])
                except Exception as skill_err:
                    pass  # Profile and provider content must not be logged.

            # 3. Cross-validate work experiences
            verified_experiences = []
            for li_exp in parsed.get('experiences', []):
                matches = student.experiences.filter(
                    company_name__iexact=li_exp.get('company_name', ''),
                    role__iexact=li_exp.get('role', '')
                )
                if matches.exists():
                    matches.update(verification_status='verified', verification_method='linkedin_pdf')
                    verified_experiences.append(li_exp.get('company_name'))

            # 4. Merge LinkedIn certifications into student profile
            existing_cert_names = {c.get('name', '').lower() for c in (student.certifications or [])}
            new_certs = []
            for cert in parsed.get('certifications', []):
                if cert.get('name', '').lower() not in existing_cert_names:
                    new_certs.append({
                        'name': cert.get('name', ''),
                        'issuer': cert.get('issuer', ''),
                        'year': cert.get('year'),
                        'url': cert.get('url'),
                    })
            if new_certs:
                student.certifications = (student.certifications or []) + new_certs

            # 5. Calculate linkedin_score
            total_linkedin_skills = len(parsed.get('skills', []))
            li_score = calculate_linkedin_score(parsed, cross_validated_count, total_linkedin_skills)
            student.linkedin_score = li_score
            student.linkedin_parsed_data = parsed

            # 6. Save LinkedIn PDF file
            uploaded_file.seek(0)
            student.linkedin_pdf = uploaded_file
            student.save()

            # 7. Recalculate trust score
            student.calculate_trust_score()


            return JsonResponse({
                'status': 'success',
                'linkedin_score': li_score,
                'cross_validated_count': cross_validated_count,
                'newly_cross_validated': newly_cross_validated,
                'added_skills': added_skills,
                'verified_experiences': verified_experiences,
                'new_certifications': [c['name'] for c in new_certs],
                'parsed_summary': {
                    'name': parsed.get('name'),
                    'headline': parsed.get('headline'),
                    'total_skills': total_linkedin_skills,
                    'total_experiences': len(parsed.get('experiences', [])),
                    'total_certifications': len(parsed.get('certifications', [])),
                    'experience_months': parsed.get('total_experience_months'),
                },
            })

        except Exception as e:
            import traceback
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==================== SMART JOB RECOMMENDATIONS VIEW ====================

class SmartJobRecommendationsView(View):
    """
    GET /api/student/<student_id>/recommendations/
    Returns top job matches + career guide (which skills to add for max impact).
    """
    def get(self, request, student_id):
        try:
            student = get_object_or_404(Student, id=student_id)
            engine = AIMatchingEngine()
            data = engine.generate_smart_recommendations(student, top_n=5)

            # Serialize gap_skills (Skill objects → dicts)
            for job in data['top_jobs']:
                job['gap_skills'] = [
                    {'id': str(s.id), 'name': s.name}
                    if hasattr(s, 'id') else s
                    for s in job['gap_skills']
                ]

            return JsonResponse({'status': 'success', 'data': data})

        except Exception as e:
            import traceback
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==================== SUPER ADMIN SETUP ====================
# ==================== SUPER ADMIN SETUP ====================
# Hardcoded super admin credentials


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
            
            # Check other admins in database
            admin = Admin.objects.filter(email=email).first()
            if admin and admin.check_password(password):
                request.session.flush()
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
            
            manual_weights = {
                'skills':   float(data.get('skills',   0.4)),
                'cgpa':     float(data.get('cgpa',     0.2)),
                'projects': float(data.get('projects', 0.2)),
                'activity': float(data.get('activity', 0.1)),
                'trust':    float(data.get('trust',    0.1)),
            }
            # Save exact manual weights first
            company.custom_weights = manual_weights
            company.save()

            # RL agent soft-learns from the human correction
            try:
                engine = AIMatchingEngine(company)
                engine.learn_from_manual_edit(company, manual_weights)
            except Exception as e:
                pass  # Profile and provider content must not be logged.

            return JsonResponse({
                'status': 'success',
                'message': 'Weights updated — agent has learned from your edit.',
                'weights': company.get_weights()
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
class WeightAgentDataView(View):
    """Return full RL history for a company — used by the chart page."""

    def get(self, request, company_id):
        company_id_session = request.session.get('company_id')
        if not company_id_session or str(company_id_session) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        company = get_object_or_404(Company, id=company_id)
        logs    = AIFeedbackLog.objects.filter(company=company).order_by('created_at')

        # Default starting weights
        defaults = {'skills': 0.4, 'cgpa': 0.2, 'projects': 0.2, 'activity': 0.1, 'trust': 0.1}

        # Build timeline: one entry per log event
        timeline = []
        for log in logs:
            timeline.append({
                'id':            str(log.id),
                'date':          log.created_at.strftime('%Y-%m-%d %H:%M'),
                'trigger':       log.trigger,
                'reward':        log.reward,
                'student_name':  log.application.student.name if log.application else '—',
                'job_title':     log.application.job.title    if log.application else '—',
                'prev_weights':  log.previous_weights,
                'new_weights':   log.adjusted_weights,
                'delta':         log.weight_delta,
                'features':      log.candidate_features,
                'reason':        log.adjustment_reason,
            })

        # Cumulative reward series
        cum_reward, cum = [], 0
        for log in logs:
            cum += log.reward
            cum_reward.append(round(cum, 2))

        return JsonResponse({
            'status':           'success',
            'company_name':     company.name,
            'initial_weights':  defaults,
            'current_weights':  company.get_weights(),
            'total_events':     logs.count(),
            'hire_count':       logs.filter(trigger='hire').count(),
            'reject_count':     logs.filter(trigger='reject').count(),
            'manual_count':     logs.filter(trigger='manual').count(),
            'timeline':         timeline,
            'cumulative_reward': cum_reward,
        })


@company_login_required
def company_ai_agent(request):
    """Render the full RL Agent visualization page."""
    company_id = request.session.get('company_id')
    company    = get_object_or_404(Company, id=company_id)
    return render(request, 'company/ai_agent.html', {
        'company_id':      str(company_id),
        'company_name':    company.name,
        'current_weights': company.get_weights(),
    })


# ==================== RECRUITMENT AGENT VIEWS ====================

@method_decorator(csrf_exempt, name='dispatch')
class RunRecruitmentAgentView(View):
    """Manual trigger: re-run the Recruitment Agent for a specific application."""

    def post(self, request, application_id):
        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        application = get_object_or_404(Application, id=application_id)

        # Security check
        if str(application.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        agent = RecruitmentAgent(company=application.job.company)
        run   = agent.run(application, triggered_by='manual')

        return JsonResponse({
            'status':    'success',
            'run_id':    str(run.id),
            'decision':  run.decision,
            'score':     round(run.score * 100, 1),
            'confidence': run.confidence,
            'run_url':   f'/company/agent-run/{run.id}/',
        })


class AgentRunsListView(View):
    """Return all agent runs for a given application (for before/after comparison)."""

    def get(self, request, application_id):
        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        application = get_object_or_404(Application, id=application_id)
        if str(application.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        runs = RecruitmentAgentRun.objects.filter(application=application)
        data = []
        for r in runs:
            data.append({
                'run_id':      str(r.id),
                'triggered_by': r.triggered_by,
                'status':      r.status,
                'score':       round(r.score * 100, 1),
                'decision':    r.decision,
                'confidence':  r.confidence,
                'weights_used': r.weights_used,
                'created_at':  r.created_at.strftime('%Y-%m-%d %H:%M'),
                'run_url':     f'/company/agent-run/{r.id}/',
            })
        return JsonResponse({'status': 'success', 'runs': data, 'count': len(data)})


class AgentRunDetailAPIView(View):
    """Return full JSON of one agent run (used by the detail page JS)."""

    def get(self, request, run_id):
        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        run = get_object_or_404(RecruitmentAgentRun, id=run_id)
        if str(run.application.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        # Sibling runs for before/after comparison
        siblings = list(
            RecruitmentAgentRun.objects
            .filter(application=run.application)
            .exclude(id=run.id)
            .values('id', 'score', 'decision', 'confidence', 'weights_used', 'triggered_by', 'created_at')
        )
        for s in siblings:
            s['id']         = str(s['id'])
            s['score']      = round(s['score'] * 100, 1)
            s['created_at'] = s['created_at'].strftime('%Y-%m-%d %H:%M')

        return JsonResponse({
            'status':          'success',
            'run_id':          str(run.id),
            'triggered_by':    run.triggered_by,
            'run_status':      run.status,
            'score':           round(run.score * 100, 1),
            'decision':        run.decision,
            'confidence':      run.confidence,
            'weights_used':    run.weights_used,
            'reasoning_steps': run.reasoning_steps,
            'fit_report':      run.fit_report,
            'created_at':      run.created_at.strftime('%Y-%m-%d %H:%M'),
            'student_name':    run.application.student.name,
            'job_title':       run.application.job.title,
            'application_id':  str(run.application.id),
            'sibling_runs':    siblings,
        })


@company_login_required
def company_agent_run_detail(request, run_id):
    """Render the agent run detail / debug page."""
    company_id  = request.session.get('company_id')
    company     = get_object_or_404(Company, id=company_id)
    run         = get_object_or_404(RecruitmentAgentRun, id=run_id)

    if str(run.application.job.company.id) != str(company_id):
        return render(request, 'vetting/error.html', {'message': 'Unauthorized'})

    # Check if interview already exists for this run
    existing_interview = AIInterview.objects.filter(agent_run=run).first()

    # Pre-compute percentage values for template (run.score is stored as 0.0-1.0)
    score_pct = round(run.score * 100, 1)

    # Pre-process feature_breakdown to convert decimals to percentages for display
    breakdown_pct = {}
    for key, v in (run.fit_report.get('feature_breakdown') or {}).items():
        breakdown_pct[key] = {
            'score_pct':        round(v.get('score', 0) * 100, 1),
            'weight_pct':       round(v.get('weight', 0) * 100, 1),
            'contribution_pct': round(v.get('contribution', 0) * 100, 1),
            'detail':           v.get('detail', ''),
        }

    # Pre-process weights_used to percentages
    weights_pct = {k: round(v * 100, 1) for k, v in (run.weights_used or {}).items()}

    return render(request, 'company/agent_run_detail.html', {
        'run':                run,
        'score_pct':          score_pct,
        'breakdown_pct':      breakdown_pct,
        'weights_pct':        weights_pct,
        'company_id':         str(company_id),
        'company_name':       company.name,
        'existing_interview': existing_interview,
    })


# ==================== AI INTERVIEW VIEWS ====================

@method_decorator(csrf_exempt, name='dispatch')
class GenerateInterviewView(View):
    """Company triggers: generate questions via Gemini, create AIInterview, send email."""

    def post(self, request, run_id):
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        from .utils.interview_generator import generate_questions
        import uuid as _uuid

        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        run = get_object_or_404(RecruitmentAgentRun, id=run_id)
        if str(run.application.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        # Don't regenerate if already exists
        try:
            existing = AIInterview.objects.filter(agent_run=run).first()
        except Exception as db_err:
            err_str = str(db_err)
            if 'no such column' in err_str or 'does not exist' in err_str:
                return JsonResponse({
                    'status': 'error',
                    'message': '⚠️ Database migration needed. Please run: python manage.py migrate — then try again.'
                }, status=500)
            return JsonResponse({'status': 'error', 'message': f'Database error: {db_err}'}, status=500)

        if existing:
            return JsonResponse({
                'status':       'exists',
                'interview_id': str(existing.id),
                'interview_url': f'/interview/{existing.token}/',
                'result_url':   f'/company/interview/{existing.id}/result/',
                'message':      'Interview already generated',
            })

        # Generate questions
        try:
            questions = generate_questions(
                student=run.application.student,
                job=run.application.job,
                agent_run=run,
            )
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Question generation failed: {e}'}, status=500)

        # Parse deadline
        try:
            data_body      = json.loads(request.body) if request.body else {}
            expires_in_days = int(data_body.get('expires_in_days', 3))
        except Exception:
            expires_in_days = 3
        from django.utils import timezone as tz
        expires_at = tz.now() + timedelta(days=expires_in_days)

        # Create interview record
        token = _uuid.uuid4().hex  # 32-char random token
        try:
            interview = AIInterview.objects.create(
                application=run.application,
                agent_run=run,
                questions=questions,
                token=token,
                status='pending',
                expires_at=expires_at,
            )
        except Exception as db_err:
            err_str = str(db_err)
            if 'no such column' in err_str or 'does not exist' in err_str:
                return JsonResponse({
                    'status': 'error',
                    'message': '⚠️ Database migration needed. Run: python manage.py migrate'
                }, status=500)
            return JsonResponse({'status': 'error', 'message': f'Failed to create interview: {db_err}'}, status=500)

        # Build interview URL
        site_url      = getattr(django_settings, 'SITE_URL', 'http://127.0.0.1:8000')
        interview_url = f'{site_url}/interview/{token}/'
        student       = run.application.student
        job           = run.application.job

        # Send email (prints to console in dev mode)
        deadline_str = expires_at.strftime('%B %d, %Y at %I:%M %p')
        email_body = f"""Dear {student.name},

Congratulations! You have been shortlisted for the position of {job.title} at {job.company.name}.

As the next step in our recruitment process, please complete your AI-powered interview.

🔗 Interview Link: {interview_url}

⏰ DEADLINE: Please complete by {deadline_str} ({expires_in_days} days from now)

Instructions:
• You will be asked 6 questions
• Type your answers carefully — an AI will evaluate your responses
• Complete all questions before the deadline
• You can pause and resume anytime before the deadline

Good luck!

Best regards,
{job.company.name} Recruitment Team
Powered by AI Talent Match"""

        try:
            send_mail(
                subject=f'Interview Invitation — {job.title} at {job.company.name}',
                message=email_body,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
                fail_silently=False,
            )
            interview.email_sent = True
            interview.save()
            email_status = 'sent'
        except Exception as e:
            email_status = f'failed: {e}'

        # In-app notification for student with the interview URL
        Notification.objects.create(
            user_id=student.id,
            user_type='student',
            type='ai_interview',
            title=f'🤖 AI Interview Ready: {job.title}',
            message=(
                f'Your AI interview for {job.title} at {job.company.name} is ready. '
                f'Answer {len(questions)} questions before {deadline_str}.'
            ),
            data={
                'interview_url': interview_url,
                'interview_id':  str(interview.id),
                'token':         token,
                'company_name':  job.company.name,
                'job_title':     job.title,
                'expires_at':    expires_at.isoformat(),
                'deadline_str':  deadline_str,
            }
        )

        return JsonResponse({
            'status':         'success',
            'interview_id':   str(interview.id),
            'interview_url':  interview_url,
            'result_url':     f'/company/interview/{interview.id}/result/',
            'email_status':   email_status,
            'question_count': len(questions),
        })


@method_decorator(csrf_exempt, name='dispatch')
class AIInterviewAnalyzeView(View):
    """
    Company triggers full Gemini analysis on a completed interview.
    POST /api/interview/<interview_id>/analyze/
    Saves result to interview.gemini_analysis and returns it.
    """
    def post(self, request, interview_id):
        from .utils.interview_generator import generate_final_report
        company_id = request.session.get('company_id')
        if not company_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        interview = get_object_or_404(AIInterview, id=interview_id)
        if str(interview.application.job.company.id) != str(company_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        if interview.status != 'completed':
            return JsonResponse({'status': 'error', 'message': 'Interview not completed yet'}, status=400)

        try:
            report = generate_final_report(interview)
            interview.gemini_analysis = report
            interview.save(update_fields=['gemini_analysis'])
            return JsonResponse({'status': 'success', 'analysis': report})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class CandidateInterviewPageView(View):
    """Candidate-facing interview page. Student must be logged in."""

    def get(self, request, token):
        student_id = request.session.get('student_id')
        if not student_id:
            # Redirect to login, preserve token in next param
            return redirect(f'/student/login/?next=/interview/{token}/')

        interview = get_object_or_404(AIInterview, token=token)

        # Security: only the candidate whose application this belongs to
        if str(interview.application.student.id) != str(student_id):
            return render(request, 'vetting/error.html',
                          {'message': 'This interview link is not for your account.'})

        if interview.is_complete():
            return redirect(f'/interview/{token}/done/')

        # Check deadline
        from django.utils import timezone as tz
        is_expired = interview.expires_at and tz.now() > interview.expires_at

        next_idx = interview.get_next_question_index()
        question = interview.questions[next_idx]

        return render(request, 'interviews/candidate_interview.html', {
            'interview':    interview,
            'question':     question,
            'q_index':      next_idx,
            'q_number':     next_idx + 1,
            'total':        len(interview.questions),
            'progress_pct': int((next_idx / len(interview.questions)) * 100),
            'token':        token,
            'is_expired':   is_expired,
        })


@method_decorator(csrf_exempt, name='dispatch')
class SubmitAnswerView(View):
    """Candidate submits one answer → Gemini scores it → return score."""

    def post(self, request, token):
        from .utils.interview_generator import score_answer
        from django.utils import timezone as tz

        student_id = request.session.get('student_id')
        if not student_id:
            return JsonResponse({'status': 'error', 'message': 'Not logged in'}, status=403)

        interview = get_object_or_404(AIInterview, token=token)
        if str(interview.application.student.id) != str(student_id):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        data   = json.loads(request.body)
        answer_text = data.get('answer', '').strip()
        q_index     = interview.get_next_question_index()

        if q_index >= len(interview.questions):
            return JsonResponse({'status': 'error', 'message': 'All questions answered'}, status=400)

        question_obj = interview.questions[q_index]

        # Score with Gemini
        result = score_answer(
            question=question_obj['question'],
            good_answer_includes=question_obj.get('good_answer_includes', ''),
            answer=answer_text,
        )

        # Save answer
        answers = list(interview.answers)
        answers.append({
            'q_index':     q_index,
            'question':    question_obj['question'],
            'answer':      answer_text,
            'score':       result['score'],
            'feedback':    result['feedback'],
            'answered_at': tz.now().isoformat(),
        })
        interview.answers = answers

        # Check if complete
        if len(answers) >= len(interview.questions):
            avg_score = sum(a['score'] for a in answers) / len(answers)
            interview.interview_score = round(avg_score * 10, 1)   # 0-100

            # Combined: 40% agent score + 60% interview score
            agent_score_pct = (interview.agent_run.score * 100) if interview.agent_run else 50
            interview.combined_score = round(
                0.40 * agent_score_pct + 0.60 * interview.interview_score, 1
            )
            interview.status       = 'completed'
            interview.completed_at = tz.now()
        elif interview.status == 'pending':
            interview.status = 'in_progress'

        interview.save()

        # ── Activity tracking: AI Interview completed ──────────────────────────
        if interview.status == 'completed':
            try:
                _student = interview.application.student
                _student.activity_score = min(float(_student.activity_score or 0) + 20, 100)
                _student.save(update_fields=['activity_score'])
            except Exception:
                pass

        # ── Notify company when interview is completed ────────────────────────
        if interview.status == 'completed':
            try:
                Notification.objects.create(
                    user_id=interview.application.job.company.id,
                    user_type='company',
                    type='ai_interview_completed',
                    title=f'🎯 AI Interview Completed: {interview.application.student.name}',
                    message=(
                        f'{interview.application.student.name} finished the AI interview for '
                        f'{interview.application.job.title}. '
                        f'Interview score: {round(interview.interview_score or 0, 1)}/100. '
                        f'Combined score: {round(interview.combined_score or 0, 1)}/100.'
                    ),
                    data={
                        'interview_id':   str(interview.id),
                        'application_id': str(interview.application.id),
                        'student_id':     str(interview.application.student.id),
                        'student_name':   interview.application.student.name,
                        'job_id':         str(interview.application.job.id),
                        'job_title':      interview.application.job.title,
                        'interview_score': round(interview.interview_score or 0, 1),
                        'combined_score':  round(interview.combined_score or 0, 1),
                    }
                )
            except Exception:
                pass
        # ─────────────────────────────────────────────────────────────────────

        return JsonResponse({
            'status':      'success',
            'score':       result['score'],
            'feedback':    result['feedback'],
            'is_complete': interview.is_complete(),
            'next_url':    f'/interview/{token}/' if not interview.is_complete() else f'/interview/{token}/done/',
        })


class InterviewDonePageView(View):
    """Final screen shown to candidate after completing all questions."""

    def get(self, request, token):
        student_id = request.session.get('student_id')
        if not student_id:
            return redirect(f'/student/login/?next=/interview/{token}/done/')

        interview = get_object_or_404(AIInterview, token=token)
        if str(interview.application.student.id) != str(student_id):
            return render(request, 'vetting/error.html', {'message': 'Unauthorized'})

        # Build per-question score list for done page
        questions = interview.questions
        answers   = interview.answers
        per_q = []
        for i, q in enumerate(questions):
            ans_obj = answers[i] if i < len(answers) else None
            if isinstance(ans_obj, dict):
                score_val = ans_obj.get('score', 0) or 0
            else:
                score_val = 0
            per_q.append({
                'question': q.get('question', '') if isinstance(q, dict) else str(q),
                'score':    score_val,
                'pct':      score_val * 10,
            })

        combined_pct = interview.combined_score  # already stored as percentage
        return render(request, 'interviews/interview_done.html', {
            'interview':          interview,
            'total_questions':    len(questions),
            'company_name':       interview.application.job.company.name,
            'per_question_scores': per_q,
            'interview_score':    round(interview.interview_score, 1) if interview.interview_score else None,
            'combined_score':     combined_pct,
            'combined_pct':       combined_pct,
        })


@company_login_required
def company_interview_result(request, interview_id):
    """Company views full interview transcript + scores."""
    company_id = request.session.get('company_id')
    interview  = get_object_or_404(AIInterview, id=interview_id)

    if str(interview.application.job.company.id) != str(company_id):
        return render(request, 'vetting/error.html', {'message': 'Unauthorized'})

    # Build qa_pairs with per-question score info
    questions = interview.questions
    answers   = interview.answers
    answer_scores = interview.answers  # list of {answer, score, feedback} or bare strings

    # Build per-question reason lookup from gemini_analysis if available
    reason_map = {}
    if interview.gemini_analysis and 'per_question' in interview.gemini_analysis:
        for pq in interview.gemini_analysis['per_question']:
            reason_map[pq.get('q_index', -1)] = pq.get('reason', '')

    # Build answer lookup by q_index for stored answers
    ans_by_idx = {}
    for a in answers:
        if isinstance(a, dict) and 'q_index' in a:
            ans_by_idx[a['q_index']] = a

    qa_pairs = []
    for i, q in enumerate(questions):
        ans_obj = ans_by_idx.get(i) or (answers[i] if i < len(answers) else None)
        if isinstance(ans_obj, dict):
            ans_text  = ans_obj.get('answer', '')
            score_val = ans_obj.get('score')
            feedback  = ans_obj.get('feedback', '')
            reason    = ans_obj.get('reason', '') or reason_map.get(i, '')
        else:
            ans_text  = ans_obj or ''
            score_val = None
            feedback  = ''
            reason    = reason_map.get(i, '')
        qa_pairs.append({
            'question': q.get('question', '') if isinstance(q, dict) else str(q),
            'type':     q.get('type', 'Question') if isinstance(q, dict) else 'Question',
            'target':   q.get('target', '') if isinstance(q, dict) else '',
            'answer':   ans_text,
            'score':    score_val,
            'score_pct': (score_val or 0) * 10,
            'feedback': feedback,
            'reason':   reason,
        })

    # Agent score as percentage (score is stored 0.0-1.0, convert to 0-100)
    agent_run = interview.agent_run
    agent_score_pct = round(agent_run.score * 100, 1) if agent_run else 0

    return render(request, 'company/interview_result.html', {
        'interview':      interview,
        'company_id':     str(company_id),
        'qa_pairs':       qa_pairs,
        'agent_score_pct': agent_score_pct,
    })


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
            
def _parse_interview_slot_config(data):
    """Validate a scheduling window before saving or generating time slots."""
    try:
        slot_date = date.fromisoformat(data['date'])
        start = datetime.strptime(data['start_time'], '%H:%M').time()
        end = datetime.strptime(data['end_time'], '%H:%M').time()
        raw_duration = data.get('slot_duration_minutes', 30)
        duration = int(raw_duration)
        if isinstance(raw_duration, bool) or duration != float(raw_duration):
            raise ValueError
        break_start = datetime.strptime(data['break_start'], '%H:%M').time() if data.get('break_start') else None
        break_end = datetime.strptime(data['break_end'], '%H:%M').time() if data.get('break_end') else None
    except (KeyError, TypeError, ValueError):
        raise ValueError('Provide a valid date, HH:MM times and an integer slot duration.')
    if slot_date < django_timezone.localdate():
        raise ValueError('Interview slots must be today or a future date.')
    if end <= start:
        raise ValueError('The end time must be after the start time.')
    window_minutes = (datetime.combine(slot_date, end) - datetime.combine(slot_date, start)).total_seconds() / 60
    if not 1 <= duration <= window_minutes:
        raise ValueError('Slot duration must be positive and fit inside the interview window.')
    if bool(break_start) != bool(break_end):
        raise ValueError('Provide both break times or leave both empty.')
    if break_start and not start <= break_start < break_end <= end:
        raise ValueError('The break must fall inside the interview window.')
    return {
        'date': slot_date, 'start_time': start, 'end_time': end,
        'slot_duration_minutes': duration, 'break_start': break_start, 'break_end': break_end,
    }


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
            config = _parse_interview_slot_config(data)
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            slot = InterviewSlot(job=job, company=job.company, **config)
            if not slot.generate_time_slots():
                return JsonResponse({'status': 'error', 'message': 'This window does not contain a full interview slot.'}, status=400)
            if not any(not s['expired'] for s in slot.generate_time_slots()):
                return JsonResponse({'status': 'error', 'message': 'The interview window must contain a future time slot.'}, status=400)
            slot.save()
            
            return JsonResponse({
                'status': 'success',
                'slot_id': str(slot.id),
                'message': 'Interview slots created successfully',
                'available_slots': slot.generate_time_slots()
            })
            
        except Http404:
            raise
        except (ValueError, TypeError) as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ScheduleInterviewView(View):
    """Book a human interview, including after a completed AI interview."""
    
    def post(self, request, application_id):
        try:
            data = json.loads(request.body)
            
            # ✅ VALIDATION: Check required fields exist
            required_fields = ['slot_id', 'date', 'start_time', 'end_time']
            for field in required_fields:
                if field not in data or not data[field]:
                    return JsonResponse({
                        'status': 'error', 
                        'message': f'Missing required field: {field}'
                    }, status=400)
            
            application = get_object_or_404(Application, id=application_id)
            company_id = request.session.get('company_id')
            
            # Security check
            if str(application.job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            # ✅ PARSE STRINGS TO DATE/TIME OBJECTS
            from datetime import datetime
            try:
                date_obj = datetime.strptime(data['date'], '%Y-%m-%d').date()
                start_time_obj = datetime.strptime(data['start_time'], '%H:%M').time()
                end_time_obj = datetime.strptime(data['end_time'], '%H:%M').time()
            except (TypeError, ValueError) as ve:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid date/time format: {str(ve)}'
                }, status=400)
            
            meeting_type = data.get('meeting_type', 'in_person')
            if meeting_type not in ('in_person', 'online', 'phone'):
                return JsonResponse({'status': 'error', 'message': 'Invalid interview type.'}, status=400)
            location = str(data.get('location') or '').strip()
            contact_person = str(data.get('contact_person') or '').strip()
            if len(location) > 500 or len(contact_person) > 200:
                return JsonResponse({'status': 'error', 'message': 'Office or contact details are too long.'}, status=400)

            # Lock the job first so competing bookings across its slot windows
            # check capacity in a consistent order on databases with row locks.
            with transaction.atomic():
                Job.objects.select_for_update().get(pk=application.job_id)
                application = Application.objects.select_for_update().get(pk=application.pk)
                if application.status not in ('shortlisted', 'interview'):
                    return JsonResponse({'status': 'error', 'message': 'Only shortlisted or interview-stage applicants can be scheduled.'}, status=400)
                existing = ScheduledInterview.objects.select_for_update().filter(application=application).first()
                if existing and existing.status != 'cancelled':
                    return JsonResponse({'status': 'error', 'message': 'A human interview is already booked for this applicant.'}, status=409)
                from django.core.exceptions import ValidationError
                try:
                    slot = InterviewSlot.objects.select_for_update().get(
                        pk=data['slot_id'], job_id=application.job_id,
                        company_id=company_id, is_active=True,
                    )
                except (InterviewSlot.DoesNotExist, ValueError, ValidationError):
                    return JsonResponse({'status': 'error', 'message': 'Choose an active slot belonging to this job.'}, status=400)
                if slot.date != date_obj:
                    return JsonResponse({'status': 'error', 'message': 'The interview date must match the selected slot.'}, status=400)
                matching = next((s for s in slot.generate_time_slots()
                                 if s['start'] == data['start_time'] and s['end'] == data['end_time']), None)
                if matching is None:
                    return JsonResponse({'status': 'error', 'message': 'Choose one of the configured interview time slots.'}, status=400)
                if matching.get('expired'):
                    return JsonResponse({'status': 'error', 'message': 'Choose a future interview time.'}, status=400)
                if not matching['available']:
                    return JsonResponse({'status': 'error', 'message': 'This time is already booked. Choose another slot.'}, status=409)

                # Preserve the existing OneToOne architecture. A cancelled
                # appointment is reused rather than creating a second record.
                interview = existing or ScheduledInterview(application=application)
                interview.slot = slot
                interview.date = date_obj
                interview.start_time = start_time_obj
                interview.end_time = end_time_obj
                interview.meeting_link = data.get('meeting_link') or ''
                interview.meeting_type = meeting_type
                interview.location = location
                interview.contact_person = contact_person
                interview.company_notes = data.get('notes') or ''
                interview.status = 'pending'
                interview.student_notes = ''
                interview.company_notified = False
                interview.student_notified = False
                interview.reminder_sent = False
                interview.save()
                
                # Update application status
                application.status = 'interview'
                application.save()
                
                # Booking and both in-app invitations succeed or roll back together.
                self._send_notifications(interview)
            
            return JsonResponse({
                'status': 'success',
                'interview_id': str(interview.id),
                'message': 'Interview scheduled successfully',
                'details': {
                    'date': data['date'],
                    'time': f"{data['start_time']} - {data['end_time']}",
                    'meeting_link': interview.meeting_link,
                    'meeting_type': interview.meeting_type,
                    'location': interview.location,
                }
            })
            
        except Http404:
            raise
        except IntegrityError:
            return JsonResponse({'status': 'error', 'message': 'This interview was already booked. Refresh and try again.'}, status=409)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Interview booking could not be saved.')
            return JsonResponse({'status': 'error', 'message': 'The interview and notifications could not be saved. Please retry.'}, status=500)
    
    def _send_notifications(self, interview):
        """Send notifications to both student and company"""
        try:
            app = interview.application
            
            # ✅ SAFE PARSING: Handle both string and date/time objects
            from datetime import datetime, date, time as dt_time
            
            # Handle date
            if isinstance(interview.date, str):
                date_obj = datetime.strptime(interview.date, '%Y-%m-%d').date()
            elif isinstance(interview.date, date):
                date_obj = interview.date
            else:
                date_obj = interview.date
            
            # Handle start_time
            if isinstance(interview.start_time, str):
                start_time_obj = datetime.strptime(interview.start_time, '%H:%M').time()
                start_display = datetime.strptime(interview.start_time, '%H:%M').strftime('%I:%M %p')
            elif isinstance(interview.start_time, dt_time):
                start_time_obj = interview.start_time
                start_display = interview.start_time.strftime('%I:%M %p')
            else:
                start_time_obj = interview.start_time
                start_display = str(interview.start_time)
            
            # Handle end_time
            if isinstance(interview.end_time, str):
                end_display = datetime.strptime(interview.end_time, '%H:%M').strftime('%I:%M %p')
            elif isinstance(interview.end_time, dt_time):
                end_display = interview.end_time.strftime('%I:%M %p')
            else:
                end_display = str(interview.end_time)
            
            formatted_date = date_obj.strftime('%A, %B %d, %Y')
            
            # Notify Student
            meeting_type = interview.meeting_type or 'in_person'
            if meeting_type == 'in_person':
                notif_title = f'🏢 In-Person Interview: {app.job.title}'
                location_line = f'\n📍 Location: {interview.location}' if interview.location else ''
                contact_line = f'\n👤 Contact: {interview.contact_person}' if interview.contact_person else ''
                notif_msg = f'You have been invited for an in-person interview at {app.job.company.name}!\n\n📅 Date: {formatted_date}\n⏰ Time: {start_display} - {end_display}{location_line}{contact_line}\n\nPlease arrive on time. Good luck!'
            else:
                notif_title = f'🎤 Interview Scheduled: {app.job.title}'
                notif_msg = f'Your interview for {app.job.title} at {app.job.company.name} has been scheduled!\n\n📅 Date: {formatted_date}\n⏰ Time: {start_display} - {end_display}\n🔗 Meeting Link: {interview.meeting_link or "Will be shared separately"}\n\nPlease join on time. Good luck!'

            Notification.objects.create(
                user_id=app.student.id,
                user_type='student',
                type='interview_scheduled',
                title=notif_title,
                message=notif_msg,
                data={
                    'interview_id': str(interview.id),
                    'job_id': str(app.job.id),
                    'job_title': app.job.title,
                    'company_name': app.job.company.name,
                    'interview_date': date_obj.isoformat() if hasattr(date_obj, 'isoformat') else str(date_obj),
                    'interview_time': start_time_obj.strftime('%H:%M') if hasattr(start_time_obj, 'strftime') else str(start_time_obj),
                    'meeting_type': meeting_type,
                    'meeting_link': interview.meeting_link or '',
                    'location': interview.location or '',
                    'contact_person': interview.contact_person or '',
                }
            )
            
            # Notify Company
            Notification.objects.create(
                user_id=app.job.company.id,
                user_type='company',
                type='interview_scheduled',
                title=f'Interview Scheduled with {app.student.name}',
                message=f'Interview scheduled for {app.student.name} on {formatted_date} at {start_display} for {app.job.title}',
                data={
                    'interview_id': str(interview.id),
                    'application_id': str(app.id),
                    'student_id': str(app.student.id),
                    'student_name': app.student.name
                }
            )
            
            # Mark as notified
            interview.student_notified = True
            interview.company_notified = True
            interview.save()
            
        except Exception:
            # Let the surrounding booking transaction preserve a consistent state.
            raise



@method_decorator(csrf_exempt, name='dispatch')
class AvailableSlotsView(View):
    """Get available time slots for a job (for scheduling dropdown)"""
    
    def get(self, request, job_id):
        try:
            job = get_object_or_404(Job, id=job_id)
            slots = InterviewSlot.objects.filter(
                job=job, 
                is_active=True,
                date__gte=django_timezone.localdate()
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


# ==================== LEADERBOARD VIEWS ====================

@student_login_required
def student_leaderboard(request):
    """Render the student leaderboard page with rich context."""
    from .models import LeaderboardEntry
    student_id = str(request.session.get('student_id', ''))
    entries = list(LeaderboardEntry.objects.select_related('student').order_by('-total_points')[:50])
    student_entry = LeaderboardEntry.objects.filter(student_id=student_id).first()

    # Bulk-fetch top 3 skills per student
    entry_ids = [e.student_id for e in entries]
    skill_rows = (
        StudentSkill.objects
        .filter(student_id__in=entry_ids)
        .select_related('skill')
        .values('student_id', 'skill__name')
        .order_by('student_id')
    )
    skill_map = {}
    for row in skill_rows:
        sid = str(row['student_id'])
        skill_map.setdefault(sid, [])
        if len(skill_map[sid]) < 3:
            skill_map[sid].append(row['skill__name'] or '')

    # Build list of plain dicts (Django templates can't access underscore attrs)
    student_rank = None
    max_pts = entries[0].total_points if entries else 1
    entry_list = []
    for i, entry in enumerate(entries, 1):
        is_you = str(entry.student_id) == student_id
        if is_you:
            student_rank = i
        entry_list.append({
            'rank': i,
            'student_name': entry.student.name,
            'student_dept': entry.student.department or '',
            'student_id_str': str(entry.student_id),
            'university': entry.university or '',
            'total_points': entry.total_points,
            'awarded_count': len(entry.awarded_actions) if entry.awarded_actions else 0,
            'skills': skill_map.get(str(entry.student_id), []),
            'pct': round(entry.total_points / max(max_pts, 1) * 100, 1),
            'is_you': is_you,
        })

    # Unique departments for filter
    departments = sorted(set(
        e['student_dept'] for e in entry_list if e['student_dept']
    ))

    # Points gap to beat rank above
    pts_to_next = None
    if student_rank and student_rank > 1:
        pts_to_next = entry_list[student_rank - 2]['total_points'] - (student_entry.total_points if student_entry else 0)

    return render(request, 'student/leaderboard.html', {
        'entry_list': entry_list,
        'podium': entry_list[:3],
        'table_rows': entry_list[3:],
        'student_entry': student_entry,
        'student_id': student_id,
        'student_rank': student_rank,
        'departments': departments,
        'pts_to_next': pts_to_next,
        'total_on_board': len(entry_list),
    })


@method_decorator(csrf_exempt, name='dispatch')
class LeaderboardView(View):
    """API: return top 50 leaderboard entries."""
    def get(self, request):
        from .models import LeaderboardEntry
        entries = LeaderboardEntry.objects.select_related('student').order_by('-total_points')[:50]
        data = [
            {
                'rank': i + 1,
                'student_name': e.student.name,
                'university': e.student.university_id,
                'department': e.student.department,
                'total_points': e.total_points,
            }
            for i, e in enumerate(entries)
        ]
        return JsonResponse({'status': 'success', 'leaderboard': data})


@company_login_required
def company_leaderboard(request):
    """Company view of the leaderboard — with match scores, offer/shortlist actions."""
    from .models import LeaderboardEntry
    company_id = str(request.session.get('company_id', ''))
    company = get_object_or_404(Company, id=company_id)

    entries = list(LeaderboardEntry.objects.select_related('student').order_by('-total_points')[:50])
    max_pts = entries[0].total_points if entries else 1

    # Bulk skills
    entry_ids = [e.student_id for e in entries]
    skill_rows = (
        StudentSkill.objects
        .filter(student_id__in=entry_ids)
        .select_related('skill')
        .values('student_id', 'skill__name')
    )
    skill_map = {}        # display: capped at 5 for chips
    full_skill_map = {}   # matching: all skills (no cap)
    for row in skill_rows:
        sid = str(row['student_id'])
        skill_name = row['skill__name'] or ''
        # full set for match scoring
        full_skill_map.setdefault(sid, set()).add(skill_name.lower())
        # display chips (capped at 5)
        skill_map.setdefault(sid, [])
        if len(skill_map[sid]) < 5:
            skill_map[sid].append(skill_name)

    # Company's active jobs and their required skills (for match score)
    active_jobs = list(Job.objects.filter(company=company, status='active').prefetch_related('required_skills'))
    job_skills_map = {str(j.id): {s.name.lower() for s in j.required_skills.all()} for j in active_jobs}

    # ── Build company demand profile ──────────────────────────────────────
    # skill_freq[skill] = number of active jobs that need this skill
    skill_freq = {}
    for js_set in job_skills_map.values():
        for sk in js_set:
            skill_freq[sk] = skill_freq.get(sk, 0) + 1

    # Extend with keywords from company description + industry (lower weight)
    import re as _re
    _SKIP = {'and','the','for','with','our','are','that','this','from','have','will','your',
             'all','can','has','was','not','but','its','who','also','they','been','more',
             'their','about','which','into','than','then','some','such','these','those'}
    _profile_text = f"{company.description or ''} {company.industry or ''}".lower()
    _profile_kws  = {w for w in _re.findall(r'\b[a-z]{3,}\b', _profile_text) if w not in _SKIP}
    for kw in _profile_kws:
        if kw not in skill_freq:
            skill_freq[kw] = 0.3   # low weight — profile keyword, not job requirement

    # Pre-compute denominator (max achievable weighted score)
    _demand_total = sum(max(v, 0.3) for v in skill_freq.values()) if skill_freq else 1

    # Students already applied / already offered
    applied_ids = set(
        Application.objects.filter(job__company=company)
        .values_list('student_id', flat=True)
    )
    # Track sent offers (stored in notifications)
    offered_ids = set(
        Notification.objects.filter(
            user_type='student', type='job_offer',
            data__company_id=company_id
        ).values_list('user_id', flat=True)
    )

    entry_list = []
    for i, entry in enumerate(entries, 1):
        sid = str(entry.student_id)
        s_skills_lower = full_skill_map.get(sid, set())  # already lowercase, all skills

        # Company-demand weighted match score
        # = Σ weight[sk] for each student skill that's in demand / total_demand * 100
        if skill_freq:
            student_weight = sum(
                max(skill_freq[sk], 0.3)
                for sk in s_skills_lower if sk in skill_freq
            )
            best_match = round(min(student_weight / _demand_total * 100, 100), 1)
        else:
            best_match = 0

        # Still track best matching job title for display hint
        best_job_id = ''
        best_job_title = ''
        _best_job_overlap = -1
        for job in active_jobs:
            js = job_skills_map[str(job.id)]
            if not js:
                continue
            overlap_count = len(s_skills_lower & js)
            if overlap_count > _best_job_overlap:
                _best_job_overlap = overlap_count
                best_job_id    = str(job.id)
                best_job_title = job.title

        entry_list.append({
            'rank': i,
            'student_id': sid,
            'student_name': entry.student.name,
            'student_dept': entry.student.department or '',
            'student_cgpa': float(entry.student.cgpa or 0),
            'trust_score': float(entry.student.trust_score or 0),
            'university': entry.university or '',
            'total_points': entry.total_points,
            'awarded_count': len(entry.awarded_actions) if entry.awarded_actions else 0,
            'skills': skill_map.get(sid, []),
            'pct': round(entry.total_points / max(max_pts, 1) * 100, 1),
            'match_score': best_match,
            'best_job_id': best_job_id,
            'best_job_title': best_job_title,
            'already_applied': entry.student_id in applied_ids,
            'offer_sent': entry.student_id in offered_ids,
        })

    departments = sorted(set(e['student_dept'] for e in entry_list if e['student_dept']))

    return render(request, 'company/leaderboard.html', {
        'entry_list': entry_list,
        'podium': entry_list[:3],
        'table_rows': entry_list[3:],
        'total_on_board': len(entry_list),
        'company': company,
        'active_jobs': active_jobs,
        'departments': departments,
    })


@method_decorator(csrf_exempt, name='dispatch')
class SendJobOfferView(View):
    """Company sends a direct job offer to a top leaderboard student."""
    def post(self, request):
        try:
            data = json.loads(request.body)
            company_id = str(request.session.get('company_id', ''))
            student_id = data.get('student_id')
            job_id     = data.get('job_id')
            salary     = data.get('salary', '')
            message    = data.get('message', '')
            deadline   = data.get('deadline', '')

            company = get_object_or_404(Company, id=company_id)
            student = get_object_or_404(Student, id=student_id)
            job_title = ''
            if job_id:
                try:
                    job = Job.objects.get(id=job_id, company=company)
                    job_title = job.title
                except Job.DoesNotExist:
                    job_title = data.get('job_title', '')
            else:
                job_title = data.get('job_title', '')

            # ── Guard 1: student already hired by this company (any job) ──────
            already_hired = Application.objects.filter(
                student=student,
                job__company=company,
                status='hired'
            ).first()
            if already_hired:
                return JsonResponse({
                    'status': 'error',
                    'code': 'already_hired',
                    'message': (
                        f'{student.name} is already hired by your company '
                        f'(for "{already_hired.job.title}"). '
                        f'You cannot send another offer to a current employee.'
                    )
                }, status=409)

            # ── Guard 2: duplicate offer for this exact job ──────────────────
            if job_id:
                duplicate_offer = Notification.objects.filter(
                    user_id=student.id,
                    user_type='student',
                    type='job_offer',
                    data__company_id=company_id,
                    data__job_id=job_id,
                ).exists()
                if duplicate_offer:
                    return JsonResponse({
                        'status': 'error',
                        'code': 'offer_already_sent',
                        'message': (
                            f'You have already sent an offer to {student.name} '
                            f'for "{job_title}". Please wait for their response.'
                        )
                    }, status=409)

                # ── Guard 3: student already applied/hired for this specific job
                existing_app = Application.objects.filter(
                    student=student,
                    job_id=job_id
                ).first()
                if existing_app and existing_app.status in ('hired', 'shortlisted', 'applied'):
                    return JsonResponse({
                        'status': 'error',
                        'code': 'already_applied',
                        'message': (
                            f'{student.name} has already applied to "{job_title}" '
                            f'(status: {existing_app.status}). No need to send an offer.'
                        )
                    }, status=409)
            # ─────────────────────────────────────────────────────────────────

            Notification.objects.create(
                user_id=student.id,
                user_type='student',
                type='job_offer',
                title=f'🎯 Job Offer from {company.name}',
                message=message or f'{company.name} wants you to join as {job_title}.',
                data={
                    'company_id': company_id,
                    'company_name': company.name,
                    'job_id': job_id or '',
                    'job_title': job_title,
                    'salary': salary,
                    'deadline': deadline,
                    'message': message,
                }
            )
            return JsonResponse({'status': 'success', 'message': 'Offer sent!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class StudentQuickPreviewView(View):
    """Return lightweight profile data for the leaderboard drawer."""
    def get(self, request, student_id):
        try:
            student = get_object_or_404(Student, id=student_id)
            skills = [
                {'name': ss.skill.name, 'verified': ss.verified_via is not None}
                for ss in StudentSkill.objects.filter(student=student).select_related('skill')[:10]
            ]
            projects = [
                {'title': p.title, 'github_url': p.github_url or ''}
                for p in Project.objects.filter(student=student)[:5]
            ]
            return JsonResponse({
                'status': 'success',
                'student': {
                    'id': str(student.id),
                    'name': student.name,
                    'email': student.email,
                    'department': student.department or '',
                    'university_id': student.university_id or '',
                    'cgpa': float(student.cgpa or 0),
                    'trust_score': float(student.trust_score or 0),
                    'profile_complete': float(student.profile_complete_score or 0) * 100,
                    'github_username': student.github_username or '',
                    'linkedin_url': student.linkedin_url or '',
                    'portfolio_url': student.portfolio_url or '',
                    'skills': skills,
                    'projects': projects,
                    'total_applications': Application.objects.filter(student=student).count(),
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class LeaderboardShortlistView(View):
    """Shortlist a student for a job directly from the leaderboard."""
    def post(self, request):
        try:
            data = json.loads(request.body)
            company_id = str(request.session.get('company_id', ''))
            company  = get_object_or_404(Company, id=company_id)
            student  = get_object_or_404(Student, id=data['student_id'])
            job      = get_object_or_404(Job, id=data['job_id'], company=company)

            app, created = Application.objects.get_or_create(
                student=student, job=job,
                defaults={'match_score': 0, 'status': 'shortlisted'}
            )
            if not created and app.status == 'applied':
                app.status = 'shortlisted'
                app.save()

            # Award points + notify student
            try:
                from .utils.points import award_points
                award_points(student, 'shortlisted', unique_key=str(app.id))
            except Exception:
                pass
            Notification.objects.create(
                user_id=student.id, user_type='student', type='shortlist',
                title=f'⭐ Shortlisted by {company.name}',
                message=f'You were shortlisted for {job.title} at {company.name} from the leaderboard!',
                data={'job_id': str(job.id), 'company_name': company.name, 'job_title': job.title}
            )
            return JsonResponse({'status': 'success', 'created': created})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class AIEffectivenessView(View):
    """API: report on how effective the AI agent decisions have been for an application."""
    def get(self, request, application_id):
        try:
            from .utils.ai_effectiveness import get_effectiveness_report
            report = get_effectiveness_report(application_id)
            return JsonResponse({'status': 'success', 'report': report})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
