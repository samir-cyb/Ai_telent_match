import json
from urllib import request
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
            assessment_type = data.get('assessment_type', 'coding')
            department_category = data.get('department_category', 'any')
            topic = data.get('topic', data.get('topic_focus', ''))
            keywords = data.get('keywords', '')
            seniority = data.get('seniority', 'any')
            custom_instructions = data.get('custom_instructions', '')
            mcq_count = int(data.get('mcq_count', 4))
            written_count = int(data.get('written_count', 2))

            # pre_generated: company already previewed + edited — skip LLM call
            pre_generated = data.get('pre_generated_data')

            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

            if pre_generated:
                # Use the already-generated (possibly edited) data directly
                challenge_data = pre_generated
            else:
                generator = QuestionGenerator()
                if assessment_type == 'mcq_written':
                    challenge_data = generator.generate_mcq_written(
                        job, difficulty, department_category,
                        topic=topic, keywords=keywords,
                        seniority=seniority, custom_instructions=custom_instructions,
                        mcq_count=mcq_count, written_count=written_count,
                    )
                else:
                    challenge_data = generator.generate_challenge(
                        job, difficulty, department_category,
                        topic=topic, keywords=keywords,
                        seniority=seniority, custom_instructions=custom_instructions,
                    )

            if assessment_type == 'mcq_written':
                defaults = {
                    'title': challenge_data['title'],
                    'description': challenge_data.get('instructions', ''),
                    'starter_code': '',
                    'test_cases': [],
                    'language': 'none',
                    'difficulty': difficulty,
                    'assessment_type': 'mcq_written',
                    'department_category': department_category,
                    'topic_focus': topic,
                    'mcq_questions': challenge_data.get('questions', []),
                    'skill_tags': [],
                    'ai_prompt_used': f'topic={topic} keywords={keywords} seniority={seniority}',
                    'is_active': True,
                }
                questions_count = len(challenge_data.get('questions', []))
            else:
                defaults = {
                    'title': challenge_data['title'],
                    'description': challenge_data['description'],
                    'starter_code': challenge_data['starter_code'],
                    'test_cases': challenge_data['test_cases'],
                    'language': challenge_data.get('language', 'python'),
                    'difficulty': difficulty,
                    'assessment_type': 'coding',
                    'department_category': department_category,
                    'topic_focus': topic,
                    'mcq_questions': [],
                    'skill_tags': challenge_data.get('skill_tags', []),
                    'ai_prompt_used': f'topic={topic} keywords={keywords} seniority={seniority}',
                    'is_active': True,
                }
                questions_count = len(challenge_data.get('test_cases', []))

            challenge, created = VettingChallenge.objects.update_or_create(
                job=job, defaults=defaults,
            )

            return JsonResponse({
                'status': 'success',
                'challenge_id': str(challenge.id),
                'assessment_type': assessment_type,
                'message': 'Assessment saved successfully',
                'data': {'title': challenge.title, 'questions_count': questions_count},
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class PreviewChallengeView(View):
    """Generate questions with AI and return them WITHOUT saving to DB.
    Company can review/edit in the frontend, then call CreateChallengeView
    with pre_generated_data to save the final version."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            job_id = data.get('job_id')
            difficulty = data.get('difficulty', 'medium')
            assessment_type = data.get('assessment_type', 'coding')
            department_category = data.get('department_category', 'any')
            topic = data.get('topic', data.get('topic_focus', ''))
            keywords = data.get('keywords', '')
            seniority = data.get('seniority', 'any')
            custom_instructions = data.get('custom_instructions', '')
            mcq_count = int(data.get('mcq_count', 4))
            written_count = int(data.get('written_count', 2))

            job = get_object_or_404(Job, id=job_id)
            company_id = request.session.get('company_id')
            if str(job.company.id) != company_id:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

            generator = QuestionGenerator()
            if assessment_type == 'mcq_written':
                challenge_data = generator.generate_mcq_written(
                    job, difficulty, department_category,
                    topic=topic, keywords=keywords,
                    seniority=seniority, custom_instructions=custom_instructions,
                    mcq_count=mcq_count, written_count=written_count,
                )
            else:
                challenge_data = generator.generate_challenge(
                    job, difficulty, department_category,
                    topic=topic, keywords=keywords,
                    seniority=seniority, custom_instructions=custom_instructions,
                )

            return JsonResponse({
                'status': 'success',
                'assessment_type': assessment_type,
                'challenge_data': challenge_data,
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
                'is_active': challenge.is_active,
                'assessment_type': challenge.assessment_type,
                'department_category': challenge.department_category,
                'topic_focus': challenge.topic_focus,
                'mcq_questions_count': len(challenge.mcq_questions),
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
            'layer3_score': float(result.layer3_ai_score) if result and result.layer3_ai_score is not None else None,
            'time_taken': self._get_time_taken(session),
            'flags': self._get_flags(session),
            'passed': result.passed if result else False,
            'submission_id': str(result.id) if result else None,
            # ADD THESE THREE LINES:
            'tab_switches': session.tab_switch_count if session else 0,
            'copy_pastes': session.copy_paste_attempts if session else 0,
            'fullscreen_exits': session.fullscreen_exits if session else 0
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
    
    
class SubmissionDetailView(View):
    """View submitted code for a specific vetting result"""
    
    def get(self, request, submission_id):
        try:
            # submission_id is actually VettingResult ID from the dashboard
            result = get_object_or_404(VettingResult, id=submission_id)
            session = result.session
            
            # Get the final code submission
            code_submission = CodeSubmission.objects.filter(
                session=session,
                is_final=True
            ).first()
            
            if not code_submission:
                # Fallback to any submission
                code_submission = CodeSubmission.objects.filter(
                    session=session
                ).first()
            
            if not code_submission:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No code submission found'
                }, status=404)
            
            return JsonResponse({
                'status': 'success',
                'code': code_submission.code,
                'language': code_submission.language,
                'test_results': result.test_case_results,
                'static_analysis': result.static_analysis_report,
                'quality_issues': result.code_quality_issues,
                'final_score': float(result.final_score) if result.final_score else 0,
                'submitted_at': session.completed_at.isoformat() if session.completed_at else None,
                'anti_cheat': {
                    'tab_switches': session.tab_switch_count,
                    'copy_pastes': session.copy_paste_attempts,
                    'fullscreen_exits': session.fullscreen_exits
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

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

        # Route to appropriate interface based on assessment type
        if challenge.assessment_type == 'mcq_written':
            import json as _json
            return render(request, 'vetting/quiz.html', {
                'session': session,
                'challenge': challenge,
                'questions_json': _json.dumps(challenge.mcq_questions),
                'time_remaining': time_remaining,
                'student_name': session.student.name,
                'token': token,
            })

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
                
                # Get anti-cheat data from request
                tab_switches = data.get('tab_switches', 0)
                copy_pastes = data.get('copy_pastes', 0)
                fullscreen_exits = data.get('fullscreen_exits', 0)
                
                # Check for cheating (basic thresholds)
                if tab_switches > 10 or copy_pastes > 10:
                    # Update session with anti-cheat data
                    session.tab_switch_count = tab_switches
                    session.copy_paste_attempts = copy_pastes
                    session.fullscreen_exits = fullscreen_exits
                    session.status = 'cheating_detected'
                    session.save()
                    
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Assessment flagged for review due to suspicious activity.'
                    }, status=403)
                
                # If not cheating, update anti-cheat data and save
                session.tab_switch_count = tab_switches
                session.copy_paste_attempts = copy_pastes
                session.fullscreen_exits = fullscreen_exits
                session.save()  # Save anti-cheat data here
                
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
                
                # Build full analysis report for storage
                ai_review = grading['details'].get('ai_review', {})
                full_report = {
                    'static_analysis':  grading['details'].get('static_analysis', {}),
                    'complexity':       grading['details'].get('complexity', {}),
                    'security':         grading['details'].get('security', {}),
                    'ai_review':        ai_review,
                    'submitted_code':   final_code,
                    'language':         session.challenge.language,
                }

                # Create result
                result = VettingResult.objects.create(
                    session=session,
                    application=session.application,
                    layer1_test_score=grading['layer1_test_score'],
                    layer2_static_score=grading['layer2_static_score'],
                    layer3_ai_score=grading['layer3_ai_score'],
                    final_score=grading['final_score'],
                    test_case_results=test_results,
                    static_analysis_report=full_report,
                    ai_feedback=ai_review.get('summary', ''),
                    code_quality_issues=grading['details'].get('quality_issues', []),
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

                result_url = f'/vetting/result/{result.id}/'
                return JsonResponse({
                    'status': 'success',
                    'score': grading['final_score'],
                    'passed': grading['passed'],
                    'layer_breakdown': {
                        'tests':   grading['layer1_test_score'],
                        'quality': grading['layer2_static_score'],
                        'ai':      grading['layer3_ai_score']
                    },
                    'result_url': result_url,
                    'message': 'Assessment submitted successfully!'
                })
                
        except Exception as e:
            import traceback
            print(traceback.format_exc())
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


class VettingResultDetailView(View):
    """Full result page — score breakdown, test cases, complexity, security, AI review."""

    def get(self, request, result_id):
        result = get_object_or_404(VettingResult, id=result_id)
        session = result.session
        challenge = session.challenge
        report = result.static_analysis_report or {}

        # Pull structured sub-sections
        static     = report.get('static_analysis', {})
        complexity = report.get('complexity', {})
        security   = report.get('security', {})
        ai_review  = report.get('ai_review', {})
        submitted_code = report.get('submitted_code', '')
        language   = report.get('language', challenge.language)

        test_results = result.test_case_results or {}
        test_details = test_results.get('details', []) if isinstance(test_results, dict) else test_results

        ctx = {
            'result':           result,
            'session':          session,
            'challenge':        challenge,
            'final_score':      float(result.final_score),
            'layer1':           float(result.layer1_test_score),
            'layer2':           float(result.layer2_static_score),
            'layer3':           float(result.layer3_ai_score or 0),
            'passed':           result.passed,
            'test_details':     test_details,
            'test_total':       test_results.get('total', 0) if isinstance(test_results, dict) else len(test_details),
            'test_passed':      test_results.get('passed', 0) if isinstance(test_results, dict) else sum(1 for t in test_details if t.get('passed')),
            'static':           static,
            'complexity':       complexity,
            'security':         security,
            'ai_review':        ai_review,
            'submitted_code':   submitted_code,
            'language':         language,
            'quality_issues':   result.code_quality_issues or [],
            'anti_cheat': {
                'tab_switches':     session.tab_switch_count,
                'copy_pastes':      session.copy_paste_attempts,
                'fullscreen_exits': session.fullscreen_exits,
            },
        }
        return render(request, 'vetting/result.html', ctx)


@method_decorator(csrf_exempt, name='dispatch')
class SubmitQuizView(View):
    """Grade MCQ + written answers and create VettingResult."""

    def post(self, request, token):
        try:
            with transaction.atomic():
                session = get_object_or_404(
                    VettingSession.objects.select_for_update(),
                    access_token=token
                )

                if session.status != 'in_progress':
                    return JsonResponse({'status': 'error', 'message': 'Invalid session state'}, status=400)

                data = json.loads(request.body)
                answers = data.get('answers', {})   # {question_id: answer_value}
                tab_switches = data.get('tab_switches', 0)
                copy_pastes = data.get('copy_pastes', 0)
                fullscreen_exits = data.get('fullscreen_exits', 0)

                # Anti-cheat check
                if tab_switches > 10 or copy_pastes > 10:
                    session.tab_switch_count = tab_switches
                    session.copy_paste_attempts = copy_pastes
                    session.fullscreen_exits = fullscreen_exits
                    session.status = 'cheating_detected'
                    session.save()
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Assessment flagged for review due to suspicious activity.'
                    }, status=403)

                session.tab_switch_count = tab_switches
                session.copy_paste_attempts = copy_pastes
                session.fullscreen_exits = fullscreen_exits
                session.save()

                challenge = session.challenge
                questions = challenge.mcq_questions

                generator = QuestionGenerator()
                total_points = 0
                earned_points = 0
                grading_details = []

                for q in questions:
                    qid = str(q.get('id'))
                    q_type = q.get('type')
                    max_pts = q.get('points', 10)
                    total_points += max_pts
                    student_answer = answers.get(qid, '')

                    if q_type == 'mcq':
                        correct = q.get('correct_answer', '').strip().upper()
                        given = str(student_answer).strip().upper()
                        # Accept just the letter or "A. text" format
                        given_letter = given[0] if given else ''
                        is_correct = given_letter == correct
                        pts = max_pts if is_correct else 0
                        earned_points += pts
                        grading_details.append({
                            'id': qid,
                            'type': 'mcq',
                            'correct': is_correct,
                            'points_earned': pts,
                            'points_max': max_pts,
                            'correct_answer': correct,
                            'student_answer': student_answer,
                            'explanation': q.get('explanation', ''),
                        })
                    elif q_type == 'written':
                        if student_answer and len(str(student_answer).strip()) > 10:
                            grade_result = generator.grade_written_answer(
                                question=q.get('question', ''),
                                rubric=q.get('grading_rubric', ''),
                                answer=student_answer,
                                max_points=max_pts,
                            )
                        else:
                            grade_result = {
                                'score': 0,
                                'feedback': 'No answer provided.',
                                'strengths': [],
                                'improvements': ['Please provide a full written answer.'],
                            }
                        pts = grade_result.get('score', 0)
                        earned_points += pts
                        grading_details.append({
                            'id': qid,
                            'type': 'written',
                            'points_earned': pts,
                            'points_max': max_pts,
                            'student_answer': student_answer,
                            'feedback': grade_result.get('feedback', ''),
                            'strengths': grade_result.get('strengths', []),
                            'improvements': grade_result.get('improvements', []),
                        })

                final_score = round((earned_points / total_points * 100), 2) if total_points > 0 else 0
                passed = final_score >= 60  # 60% passing threshold for MCQ/written

                # Create VettingResult — layer1=MCQ%, layer2=0, layer3=Written%
                mcq_items = [d for d in grading_details if d['type'] == 'mcq']
                written_items = [d for d in grading_details if d['type'] == 'written']
                mcq_total = sum(d['points_max'] for d in mcq_items)
                mcq_earned = sum(d['points_earned'] for d in mcq_items)
                written_total = sum(d['points_max'] for d in written_items)
                written_earned = sum(d['points_earned'] for d in written_items)

                layer1 = round((mcq_earned / mcq_total * 100), 2) if mcq_total > 0 else 0
                layer3 = round((written_earned / written_total * 100), 2) if written_total > 0 else 0

                result = VettingResult.objects.create(
                    session=session,
                    application=session.application,
                    layer1_test_score=layer1,
                    layer2_static_score=0,
                    layer3_ai_score=layer3,
                    final_score=final_score,
                    test_case_results=grading_details,
                    static_analysis_report={},
                    ai_feedback='; '.join(
                        d.get('feedback', '') for d in written_items if d.get('feedback')
                    ),
                    code_quality_issues=[],
                    passed=passed,
                )

                session.status = 'completed'
                session.completed_at = timezone.now()
                session.save()

                app = session.application
                app.vetting_score = final_score
                app.save()

                # Notify company
                from core.models import Notification
                Notification.objects.create(
                    user_id=session.challenge.job.company.id,
                    user_type='company',
                    type='vetting_completed',
                    title=f'Assessment Completed: {session.student.name}',
                    message=f'{session.student.name} scored {final_score}% on the MCQ + Written assessment.',
                    data={
                        'application_id': str(app.id),
                        'score': final_score,
                        'passed': passed,
                    }
                )

                return JsonResponse({
                    'status': 'success',
                    'score': final_score,
                    'passed': passed,
                    'layer_breakdown': {
                        'mcq': layer1,
                        'written': layer3,
                    },
                    'details': grading_details,
                    'message': 'Assessment submitted successfully!',
                })

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)