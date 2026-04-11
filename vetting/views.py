import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.shortcuts import redirect  # Add this if not present

from core.models import Job, Student, Application, Company
from .models import VettingChallenge, VettingSession, VettingResult, CodeSubmission
from .services import QuestionGenerator, CodeExecutor, CodeGrader

# ==================== COMPANY VIEWS ====================

@method_decorator(csrf_exempt, name='dispatch')
class CreateChallengeView(View):
    """Generate AI challenge for a job"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            job_id = data.get('job_id')
            difficulty = data.get('difficulty', 'medium')
            
            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            
            # Security check
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            # Generate challenge
            generator = QuestionGenerator()
            challenge_data = generator.generate_challenge(job, difficulty)
            
            # Save to database
            challenge, created = VettingChallenge.objects.update_or_create(
                job=job,
                defaults={
                    'title': challenge_data['title'],
                    'description': challenge_data['description'],
                    'starter_code': challenge_data['starter_code'],
                    'test_cases': challenge_data['test_cases'],
                    'language': challenge_data.get('language', 'python'),
                    'difficulty': difficulty,
                    'skill_tags': challenge_data.get('skill_tags', []),
                    'ai_prompt_used': str(challenge_data),
                    'is_active': True
                }
            )
            
            return JsonResponse({
                'status': 'success',
                'challenge_id': str(challenge.id),
                'message': 'Assessment created successfully',
                'data': {
                    'title': challenge.title,
                    'test_cases_count': len(challenge_data['test_cases'])
                }
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

class CompanyVettingDashboardView(View):
    """View all candidates and their vetting scores for a job"""
    
    def get(self, request, job_id):
        job = get_object_or_404(Job, id=job_id)
        company_id = request.session.get('company_id')
        
        if str(job.company.id) != company_id:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        
        # Get challenge details
        challenge_data = None
        try:
            challenge = job.vetting_challenge
            challenge_data = {
                'title': challenge.title,
                'description': challenge.description,
                'starter_code': challenge.starter_code,
                'test_cases': challenge.test_cases,
                'difficulty': challenge.difficulty,
                'language': challenge.language,
                'time_limit': challenge.time_limit_minutes,
                'created_at': challenge.created_at.isoformat() if challenge.created_at else None,
                'is_active': challenge.is_active
            }
        except VettingChallenge.DoesNotExist:
            challenge_data = None
        
        # Get all applications with vetting results
        applications = Application.objects.filter(job=job).select_related(
            'student', 'vetting_result', 'vetting_session'
        ).order_by('-vetting_result__final_score')
        
        data = []
        for rank, app in enumerate(applications, 1):
            result = getattr(app, 'vetting_result', None)
            session = getattr(app, 'vetting_session', None)
            
            item = {
            'rank': rank,
            'application_id': str(app.id),
            'student_name': app.student.name,
            'student_id': str(app.student.id),
            'status': app.status,
            'match_score': float(app.match_score) if app.match_score else 0,
            'vetting_status': session.status if session else 'not_started',
            'final_score': float(result.final_score) if result and result.final_score else None,
            'layer1_score': float(result.layer1_test_score) if result and result.layer1_test_score else None,
            'layer2_score': float(result.layer2_static_score) if result and result.layer2_static_score else None,
            'layer3_score': float(result.layer3_ai_score) if result and result.layer3_ai_score is not None else None,  # FIX HERE
            'time_taken': self._get_time_taken(session),
            'flags': self._get_flags(session),
            'passed': result.passed if result else False,
            'submission_id': str(result.id) if result else None
        }
            data.append(item)
        
        return JsonResponse({
            'status': 'success',
            'job_title': job.title,
            'job_id': str(job.id),
            'candidates': data,
            'total_assessed': len([d for d in data if d['final_score'] is not None]),
            'pass_count': len([d for d in data if d['passed']]),
            'challenge': challenge_data
        })
    
    def _get_time_taken(self, session):
        if not session or not session.started_at or not session.completed_at:
            return None
        delta = session.completed_at - session.started_at
        return int(delta.total_seconds() / 60)
    
    def _get_flags(self, session):
        if not session:
            return []
        flags = []
        if session.tab_switch_count > 3:
            flags.append('excessive_tab_switching')
        if session.copy_paste_attempts > 5:
            flags.append('copy_paste_detected')
        if session.fullscreen_exits > 0:
            flags.append('fullscreen_exit')
        return flags

@method_decorator(csrf_exempt, name='dispatch')
class GenerateAssessmentTokenView(View):
    """Generate access token for student to take assessment"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            application_id = data.get('application_id')
            
            application = get_object_or_404(Application, id=application_id)
            company_id = request.session.get('company_id')
            
            # Security check
            if str(application.job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            
            # Check if challenge exists
            if not hasattr(application.job, 'vetting_challenge'):
                return JsonResponse({
                    'status': 'error', 
                    'message': 'No assessment created for this job yet'
                }, status=400)
            
            challenge = application.job.vetting_challenge
            
            # Create or get session
            session, created = VettingSession.objects.get_or_create(
            application=application,
            defaults={
                'challenge': challenge,
                'student': application.student,
                'window_start': timezone.now(),
                'window_end': timezone.now() + timedelta(days=7),
                'max_duration_minutes': challenge.time_limit_minutes,
                'token_expires_at': timezone.now() + timedelta(days=7)  # ADD THIS LINE
            }
        )
            
            # Generate notification to student
            from core.models import Notification
            Notification.objects.create(
                user_id=application.student.id,
                user_type='student',
                type='vetting_invitation',
                title=f'Technical Assessment: {challenge.title}',
                message=f'You have been invited to complete a technical assessment for {application.job.title}. You have 7 days to start the test.',
                data={
                    'application_id': str(application.id),
                    'token': session.access_token,
                    'test_url': f'/vetting/test/{session.access_token}/'
                }
            )
            
            return JsonResponse({
                'status': 'success',
                'token': session.access_token,
                'expires_at': session.window_end.isoformat(),
                'test_url': f'/vetting/test/{session.access_token}/'
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ==================== STUDENT VIEWS ====================

class TestInterfaceView(View):
    """Render the IDE interface for taking test"""
    
    def get(self, request, token):
        session = get_object_or_404(VettingSession, access_token=token)
        
        # Check if student is logged in (hybrid auth)
        student_id = request.session.get('student_id')
        if student_id and str(session.student.id) != student_id:
            return render(request, 'vetting/error.html', {
                'message': 'This assessment is linked to a different account.'
            })
        
        # Check validity
        if not session.is_token_valid():
            return render(request, 'vetting/error.html', {
                'message': 'This assessment link has expired.'
            })
        
        if session.status == 'completed':
            return render(request, 'vetting/error.html', {
                'message': 'You have already completed this assessment.'
            })
        
        if session.status == 'cheating_detected':
            return render(request, 'vetting/error.html', {
                'message': 'Assessment locked due to suspicious activity.'
            })
        
        # Check if window is open
        if not session.can_start():
            if timezone.now() < session.window_start:
                return render(request, 'vetting/error.html', {
                    'message': f'Assessment will be available on {session.window_start.strftime("%Y-%m-%d %H:%M")}'
                })
            else:
                return render(request, 'vetting/error.html', {
                    'message': 'Assessment window has closed.'
                })
        
        # Start the session if not started
        if session.status == 'pending':
            session.status = 'in_progress'
            session.started_at = timezone.now()
            session.ip_address = self.get_client_ip(request)
            session.user_agent = request.META.get('HTTP_USER_AGENT', '')
            session.save()
        
        # Check time remaining
        time_remaining = session.get_time_remaining_seconds()
        if time_remaining <= 0:
            return self._auto_submit(session)
        
        challenge = session.challenge
        
        return render(request, 'vetting/ide.html', {
            'session': session,
            'challenge': challenge,
            'starter_code': challenge.starter_code,
            'language': challenge.language,
            'time_remaining': time_remaining,
            'student_name': session.student.name
        })
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')

@method_decorator(csrf_exempt, name='dispatch')
class ExecuteCodeView(View):
    """AJAX endpoint to execute code during test"""
    
    def post(self, request, token):
        try:
            data = json.loads(request.body)
            session = get_object_or_404(VettingSession, access_token=token)
            
            # Validate session state
            if session.status != 'in_progress':
                return JsonResponse({'status': 'error', 'message': 'Session not active'}, status=400)
            
            if not session.has_time_remaining():
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Time expired',
                    'redirect': '/vetting/expired/'
                }, status=400)
            
            code = data.get('code', '')
            language = data.get('language', session.challenge.language)
            
            # Save submission (not final)
            submission = CodeSubmission.objects.create(
                session=session,
                code=code,
                language=language,
                is_final=False
            )
            
            # Execute code
            executor = CodeExecutor()
            
            # If test cases requested, run them
            if data.get('run_tests', False):
                results = executor.run_test_cases(
                    code, 
                    language, 
                    session.challenge.test_cases
                )
                submission.test_cases_passed = results['passed']
                submission.total_test_cases = results['total']
                submission.save()
                
                return JsonResponse({
                    'status': 'success',
                    'results': results,
                    'time_remaining': session.get_time_remaining_seconds()
                })
            else:
                # Just run with sample input
                result = executor.execute(
                    code, 
                    language, 
                    data.get('stdin', '')
                )
                return JsonResponse({
                    'status': 'success',
                    'output': result,
                    'time_remaining': session.get_time_remaining_seconds()
                })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class SubmitTestView(View):
    """Final submission and grading"""
    
    def post(self, request, token):
        try:
            with transaction.atomic():
                session = get_object_or_404(
                    VettingSession.objects.select_for_update(), 
                    access_token=token
                )
                
                if session.status != 'in_progress':
                    return JsonResponse({
                        'status': 'error', 
                        'message': 'Invalid session state'
                    }, status=400)
                
                data = json.loads(request.body)
                final_code = data.get('code', '')
                
                # Get anti-cheat data
                session.tab_switch_count = data.get('tab_switches', session.tab_switch_count)
                session.copy_paste_attempts = data.get('copy_pastes', session.copy_paste_attempts)
                session.fullscreen_exits = data.get('fullscreen_exits', session.fullscreen_exits)
                
                # Check for cheating (basic thresholds)
                if session.tab_switch_count > 10 or session.copy_paste_attempts > 10:
                    session.status = 'cheating_detected'
                    session.save()
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Assessment flagged for review due to suspicious activity.'
                    }, status=403)
                
                # Final execution with all test cases
                executor = CodeExecutor()
                test_results = executor.run_test_cases(
                    final_code,
                    session.challenge.language,
                    session.challenge.test_cases
                )
                
                # Save final submission
                CodeSubmission.objects.create(
                    session=session,
                    code=final_code,
                    language=session.challenge.language,
                    is_final=True,
                    test_cases_passed=test_results['passed'],
                    total_test_cases=test_results['total']
                )
                
                # 3-Layer Grading
                grader = CodeGrader()
                grading = grader.grade(
                    final_code,
                    test_results,
                    session.challenge.language
                )
                
                # Create result
                result = VettingResult.objects.create(
                    session=session,
                    application=session.application,
                    layer1_test_score=grading['layer1_test_score'],
                    layer2_static_score=grading['layer2_static_score'],
                    layer3_ai_score=grading['layer3_ai_score'],
                    final_score=grading['final_score'],
                    test_case_results=test_results,
                    static_analysis_report=grading['details']['static_analysis'],
                    code_quality_issues=grading['details']['quality_issues'],
                    passed=grading['passed']
                )
                
                # Update session
                session.status = 'completed'
                session.completed_at = timezone.now()
                session.save()
                
                # Update Application with vetting score
                app = session.application
                app.vetting_score = grading['final_score']
                app.save()
                
                # Notify company
                from core.models import Notification
                Notification.objects.create(
                    user_id=session.challenge.job.company.id,
                    user_type='company',
                    type='vetting_completed',
                    title=f'Assessment Completed: {session.student.name}',
                    message=f'{session.student.name} scored {grading["final_score"]}% on the technical assessment.',
                    data={
                        'application_id': str(app.id),
                        'score': grading['final_score'],
                        'passed': grading['passed']
                    }
                )
                
                return JsonResponse({
                    'status': 'success',
                    'score': grading['final_score'],
                    'passed': grading['passed'],
                    'layer_breakdown': {
                        'tests': grading['layer1_test_score'],
                        'quality': grading['layer2_static_score'],
                        'ai': grading['layer3_ai_score']
                    },
                    'message': 'Assessment submitted successfully!'
                })
                
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    def _auto_submit(self, session):
        """Handle time expiration"""
        if session.status == 'in_progress':
            # Get last code submission
            last_sub = CodeSubmission.objects.filter(
                session=session
            ).order_by('-submitted_at').first()
            
            if last_sub:
                # Submit with last code
                class FakeRequest:
                    def __init__(self, body):
                        self._body = body
                    def json(self):
                        return json.loads(self._body)
                
                fake_req = FakeRequest(json.dumps({
                    'code': last_sub.code,
                    'tab_switches': session.tab_switch_count,
                    'copy_pastes': session.copy_paste_attempts,
                    'fullscreen_exits': session.fullscreen_exits
                }))
                return self.post(fake_req, session.access_token)
        
        return render(request, 'vetting/expired.html')
    
# ==================== STUDENT VIEWS ====================

class StudentPendingAssessmentsView(View):
    """Show list of pending technical assessments for logged-in student"""
    
    def get(self, request):
        student_id = request.session.get('student_id')
        
        if not student_id:
            return redirect('/student/login/')  # or your login URL
        
        student = get_object_or_404(Student, id=student_id)
        
        # Get all pending vetting sessions for this student
        pending_sessions = VettingSession.objects.filter(
            student=student,
            status__in=['pending', 'in_progress'],
            window_end__gt=timezone.now()
        ).select_related('challenge', 'challenge__job', 'application')
        
        assessments = []
        for session in pending_sessions:
            time_remaining = None
            if session.status == 'in_progress' and session.started_at:
                elapsed = (timezone.now() - session.started_at).total_seconds()
                total_seconds = session.max_duration_minutes * 60
                time_remaining = max(0, total_seconds - elapsed)
            
            assessments.append({
                'session_id': str(session.id),
                'token': session.access_token,
                'job_title': session.challenge.job.title,
                'company_name': session.challenge.job.company.name,
                'challenge_title': session.challenge.title,
                'difficulty': session.challenge.difficulty,
                'status': session.status,
                'window_start': session.window_start,
                'window_end': session.window_end,
                'time_limit_minutes': session.max_duration_minutes,
                'time_remaining_seconds': time_remaining,
                'test_url': f'/vetting/test/{session.access_token}/'
            })
        
        return render(request, 'vetting/student_pending.html', {
            'assessments': assessments,
            'student_name': student.name,
            'total_pending': len(assessments)
        })