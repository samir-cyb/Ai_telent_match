"""Offline regression tests for the audit's observable failures."""
import io
import json
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import URLResolver, get_resolver
from django.utils import timezone

from .models import (Admin, Application, Company, Job, Notification, PipelineCandidate,
                     PipelineRun, Project, Student, WorkExperience)


class SystemRepairTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = Student.objects.create(name='Student', email='student@example.test',
                                              department='CSE', university_id='S1', cgpa=3.5)
        self.student.set_password('student-test-password')
        self.student.save()
        self.other = Student.objects.create(name='Other', email='other@example.test', department='CSE', university_id='S2')
        self.company = Company.objects.create(name='Company', email='company@example.test', industry='Software', size='Startup')
        self.other_company = Company.objects.create(name='Other Co', email='otherco@example.test', industry='Software', size='Startup')
        self.job = Job.objects.create(company=self.company, title='Python developer', description='Build APIs', job_type='Remote')
        self.profile = f'/api/student/{self.student.pk}/profile/'
        self.login('student', self.student)

    def login(self, role, obj, client=None):
        client = client or self.client
        session = client.session
        for r in ('student', 'company', 'admin'):
            session.pop(r + '_id', None)
        session['user_type'] = role
        session[role + '_id'] = str(obj.pk)
        session.save()
        return client

    def send(self, path, data, method='post', client=None):
        return getattr(client or self.client, method)(path, json.dumps(data), content_type='application/json')

    def test_anonymous_profile_write_is_denied(self):
        self.assertEqual(self.send(self.profile, {'name': 'Intruder'}, 'put', Client()).status_code, 401)

    def test_other_student_profile_read_is_denied(self):
        self.login('student', self.other)
        self.assertEqual(self.client.get(self.profile).status_code, 403)

    def test_other_student_profile_write_is_denied(self):
        self.login('student', self.other)
        self.assertEqual(self.send(self.profile, {'name': 'Wrong'}, 'put').status_code, 403)

    def test_profile_clear_fields_and_zero_cgpa(self):
        response = self.send(self.profile, {'cgpa': 0, 'portfolio_url': '', 'graduation_date': None, 'projects': []}, 'put')
        self.assertEqual(response.status_code, 200, response.content)
        self.student.refresh_from_db()
        self.assertEqual(float(self.student.cgpa), 0)
        self.assertEqual(self.student.portfolio_url, '')

    def test_registration_preserves_zero_cgpa(self):
        response = self.send('/api/auth/student/register/', {
            'name': 'Zero CGPA', 'email': 'zero@example.test',
            'password': 'student-test-password', 'department': 'CSE',
            'university_id': 'ZERO1', 'cgpa': 0,
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(Student.objects.get(email='zero@example.test').cgpa), 0)

    def test_invalid_date_preserves_existing_profile(self):
        Project.objects.create(student=self.student, title='Keep')
        response = self.send(self.profile, {'name': 'Changed', 'projects': [], 'experiences': [{'role': 'Dev', 'start_date': 'not-date'}]}, 'put')
        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, 'Student')
        self.assertTrue(self.student.projects.filter(title='Keep').exists())

    def test_late_profile_failure_rolls_back(self):
        WorkExperience.objects.create(student=self.student, company_name='Keep', role='Dev', start_date='2025-01-01')
        with patch('core.views.WorkExperience.objects.create', side_effect=RuntimeError('test failure')):
            response = self.send(self.profile, {'name': 'Changed', 'experiences': [{'company': 'New', 'role': 'Dev', 'start_date': '2026-01-01'}]}, 'put')
        self.assertEqual(response.status_code, 500)
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, 'Student')
        self.assertTrue(self.student.experiences.filter(company_name='Keep').exists())

    def test_client_cannot_mark_project_verified(self):
        response = self.send(self.profile, {'projects': [{'title': 'Manual', 'verified': True}]}, 'put')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(self.student.projects.get().verified)

    def test_explicit_empty_project_list_removes_projects(self):
        Project.objects.create(student=self.student, title='Remove intentionally')
        self.assertEqual(self.send(self.profile, {'projects': []}, 'put').status_code, 200)
        self.assertFalse(self.student.projects.exists())

    def test_skill_url_uuid_is_used(self):
        response = self.send(f'/api/student/{self.student.pk}/skills/', {'skill_name': 'Python', 'proficiency_level': 'Intermediate', 'student_id': str(self.other.pk)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.student.student_skills.filter(skill__name='python').exists())
        self.assertFalse(self.other.student_skills.exists())

    def test_experience_endpoint_signature(self):
        response = self.send(f'/api/student/{self.student.pk}/experience/', {'company_name': 'Test', 'role': 'Dev', 'start_date': '2025-01-01'})
        self.assertEqual(response.status_code, 200, response.content)

    def test_preferences_endpoint_signature_and_merge(self):
        response = self.send(f'/api/student/{self.student.pk}/preferences/', {'preferences': {'job_types': ['Remote']}})
        self.assertEqual(response.status_code, 200, response.content)
        self.student.refresh_from_db()
        self.assertEqual(self.student.preferences['job_types'], ['Remote'])

    def test_dashboard_missing_record_returns_404(self):
        from .views import StudentDashboardView
        response = StudentDashboardView().get(RequestFactory().get('/'), uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_admin_analytics_requires_login(self):
        self.assertEqual(Client().get('/api/admin/analytics/').status_code, 401)

    def test_application_update_requires_company(self):
        app = Application.objects.create(student=self.student, job=self.job)
        self.assertEqual(self.send('/api/application/update/', {'application_id': str(app.pk), 'status': 'hired'}, client=Client()).status_code, 401)

    def test_company_cannot_update_another_company_application(self):
        app = Application.objects.create(student=self.student, job=self.job)
        self.login('company', self.other_company)
        self.assertEqual(self.send('/api/application/update/', {'application_id': str(app.pk), 'status': 'rejected'}).status_code, 403)

    def test_application_status_validation(self):
        app = Application.objects.create(student=self.student, job=self.job)
        self.login('company', self.company)
        response = self.send('/api/application/update/', {'application_id': str(app.pk), 'status': 'anything'})
        self.assertEqual(response.status_code, 400)
        app.refresh_from_db()
        self.assertEqual(app.status, 'applied')

    def test_repeat_status_update_is_idempotent(self):
        app = Application.objects.create(student=self.student, job=self.job)
        self.login('company', self.company)
        data = {'application_id': str(app.pk), 'status': 'interview'}
        self.assertEqual(self.send('/api/application/update/', data).status_code, 200)
        self.assertEqual(self.send('/api/application/update/', data).status_code, 200)
        self.assertEqual(Notification.objects.filter(type='status_interview').count(), 1)

    def test_malformed_json_is_400(self):
        self.assertEqual(self.client.put(self.profile, '{', content_type='application/json').status_code, 400)

    def test_csrf_required_for_mutation(self):
        client = self.login('student', self.student, Client(enforce_csrf_checks=True))
        self.assertEqual(self.send(self.profile, {'name': 'Changed'}, 'put', client).status_code, 403)
        client.get('/student/profile/')
        token = client.cookies['csrftoken'].value
        response = client.put(self.profile, json.dumps({'name': 'Changed'}), content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)

    def test_invalid_upload_is_rejected(self):
        file = SimpleUploadedFile('fake.pdf', b'not a PDF', 'application/pdf')
        response = self.client.post(f'/api/student/{self.student.pk}/upload-resume/', {'resume': file})
        self.assertEqual(response.status_code, 400)

    def test_resume_parser_failure_does_not_save_file(self):
        file = SimpleUploadedFile('cv.pdf', b'%PDF-test', 'application/pdf')
        with patch('core.views.ResumeParser.parse_resume', return_value={'parse_status': 'failed', 'error': 'Provider unavailable'}):
            response = self.client.post(f'/api/student/{self.student.pk}/upload-resume/', {'resume': file})
        self.assertEqual(response.status_code, 422)
        self.student.refresh_from_db()
        self.assertFalse(self.student.resume)

    def test_linkedin_parser_failure_preserves_file(self):
        file = SimpleUploadedFile('profile.pdf', b'%PDF-test', 'application/pdf')
        with patch('core.utils.linkedin_parser.LinkedInParser.parse', return_value={'parse_status': 'failed', 'error': 'Unavailable'}):
            response = self.client.post(f'/api/student/{self.student.pk}/upload-linkedin/', {'linkedin_pdf': file})
        self.assertEqual(response.status_code, 422)
        self.student.refresh_from_db()
        self.assertFalse(self.student.linkedin_pdf)

    def test_parsers_explicitly_report_failure(self):
        from .utils.resume_parser import ResumeParser
        from .utils.linkedin_parser import LinkedInParser
        self.assertEqual(ResumeParser().parse_resume(io.BytesIO(b'invalid'))['parse_status'], 'failed')
        self.assertEqual(LinkedInParser().parse(io.BytesIO(b'invalid'))['parse_status'], 'failed')

    def test_github_url_normalization(self):
        from .validation import github_handle
        self.assertEqual(github_handle('https://github.com/BzShezan/'), 'BzShezan')
        with self.assertRaises(Exception):
            github_handle('https://evil.example/BzShezan')

    def test_github_sync_is_repeatable_and_keeps_manual_project(self):
        self.student.github_username = 'https://github.com/example/'
        self.student.save()
        Project.objects.create(student=self.student, title='Manual')
        result = {'valid': True, 'score': 80, 'verified_projects': [{'id': 123, 'name': 'API', 'url': 'https://github.com/example/API', 'language': 'Python', 'description': 'Project'}]}
        with patch('core.utils.github_scraper.GitHubValidator.validate_student_github', return_value=result):
            path = f'/api/student/{self.student.pk}/github/sync/'
            self.assertEqual(self.client.post(path).status_code, 200)
            self.assertEqual(self.client.post(path).status_code, 200)
        self.assertEqual(self.student.projects.count(), 2)
        self.assertTrue(self.student.projects.get(github_repo_id=123).verified)

    def test_github_failure_preserves_projects(self):
        self.student.github_username = 'example'
        self.student.save()
        Project.objects.create(student=self.student, title='Keep')
        with patch('core.utils.github_scraper.GitHubValidator.validate_student_github', return_value={'valid': False, 'error': 'Rate limit'}):
            response = self.client.post(f'/api/student/{self.student.pk}/github/sync/')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.student.projects.count(), 1)

    @override_settings(GITHUB_TOKEN='')
    def test_empty_github_token_omits_authorization(self):
        from .utils.github_scraper import GitHubValidator
        self.assertNotIn('Authorization', GitHubValidator().headers)

    def test_python_uses_sandbox_and_plain_stdout(self):
        from vetting.services.code_executor import CodeExecutor
        response = Mock(status_code=201)
        response.json.return_value = {'status': {'id': 3, 'description': 'Accepted'}, 'stdout': 'YWJj'}
        with patch('vetting.services.code_executor.requests.post', return_value=response) as post:
            self.assertEqual(CodeExecutor().execute('print(1)', 'python')['stdout'], 'YWJj')
        self.assertFalse(post.call_args.kwargs['json']['enable_network'])
        self.assertEqual(post.call_args.kwargs['json']['language_id'], 71)

    def test_sandbox_unavailable_does_not_grade_as_wrong_answer(self):
        from vetting.services.code_executor import CodeExecutor, SandboxUnavailable
        with patch('vetting.services.code_executor.requests.post', side_effect=__import__('requests').ConnectionError):
            with self.assertRaises(SandboxUnavailable):
                CodeExecutor().run_test_cases('print(1)', 'python', [{'input': '', 'expected': '1'}])

    def test_application_database_uniqueness(self):
        Application.objects.create(student=self.student, job=self.job)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Application.objects.create(student=self.student, job=self.job)

    def test_points_are_idempotent_per_event(self):
        from .utils.points import award_points
        self.assertEqual(award_points(self.student, 'hired', 'a'), 50)
        self.assertEqual(award_points(self.student, 'hired', 'a'), 50)
        self.assertEqual(award_points(self.student, 'hired', 'b'), 100)

    def test_trust_snapshot_does_not_overwrite_new_profile_fields(self):
        snapshot = Student.objects.get(pk=self.student.pk)
        Student.objects.filter(pk=self.student.pk).update(name='Newer edit')
        snapshot.calculate_trust_score()
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, 'Newer edit')

    def test_admin_password_rotation_revokes_only_its_sessions(self):
        from django.core.management import call_command
        from django.contrib.sessions.models import Session
        admin = Admin.objects.create(email='rotate@example.test', is_super_admin=True)
        admin.set_password('old-private-test-password')
        admin.save()
        client = self.login('admin', admin, Client())
        admin_key = client.session.session_key
        student_key = self.client.session.session_key
        with patch('core.management.commands.change_platform_admin_password.getpass.getpass', return_value='new-private-test-password-2026'):
            call_command('change_platform_admin_password', email=admin.email, stdout=io.StringIO())
        admin.refresh_from_db()
        self.assertTrue(admin.check_password('new-private-test-password-2026'))
        self.assertFalse(Session.objects.filter(pk=admin_key).exists())
        self.assertTrue(Session.objects.filter(pk=student_key).exists())

    def test_counter_reconciliation_preview_does_not_mutate(self):
        from django.core.management import call_command
        Application.objects.create(student=self.student, job=self.job)
        Job.objects.filter(pk=self.job.pk).update(total_applicants=9)
        call_command('reconcile_applicant_counts', stdout=io.StringIO())
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_applicants, 9)
        call_command('reconcile_applicant_counts', apply=True, stdout=io.StringIO())
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_applicants, 1)

    def test_pipeline_generation_failure_rolls_back_elimination(self):
        from .utils.pipeline_engine import approve_sort_and_send_vetting
        app = Application.objects.create(student=self.student, job=self.job)
        pipeline = PipelineRun.objects.create(job=self.job, created_by=self.company, stage='sort_review')
        candidate = PipelineCandidate.objects.create(pipeline=pipeline, application=app, sort_score=80, sort_rank=1, stage='sort')
        with patch('core.utils.pipeline_engine._ensure_vetting_challenge', side_effect=RuntimeError('provider failed')):
            with self.assertRaises(RuntimeError):
                approve_sort_and_send_vetting(pipeline, [], timezone.now() + timedelta(days=1))
        candidate.refresh_from_db()
        pipeline.refresh_from_db()
        self.assertEqual(candidate.stage, 'sort')
        self.assertEqual(pipeline.stage, 'sort_review')

    def test_chat_room_ownership(self):
        from .consumers import application_room_allowed
        app = Application.objects.create(student=self.student, job=self.job)
        self.assertTrue(application_room_allowed(app.pk, student_id=self.student.pk))
        self.assertTrue(application_room_allowed(app.pk, company_id=self.company.pk))
        self.assertFalse(application_room_allowed(app.pk, student_id=self.other.pk))

    def test_all_class_api_routes_have_a_policy(self):
        from .permissions import PUBLIC, TOKEN, STUDENT, COMPANY, ADMIN, SHARED
        known = PUBLIC | TOKEN | STUDENT | COMPANY | ADMIN | SHARED
        def walk(patterns):
            for p in patterns:
                if isinstance(p, URLResolver):
                    if p.app_name != 'admin':
                        yield from walk(p.url_patterns)
                elif hasattr(p.callback, 'view_class'):
                    yield p.callback.view_class.__name__
        self.assertEqual(set(walk(get_resolver().url_patterns)) - known, set())

    def test_admin_login_uses_database_password(self):
        admin = Admin.objects.create(email='admin@example.test', is_super_admin=True)
        admin.set_password('private-test-password')
        admin.save()
        response = self.send('/api/auth/admin/login/', {'email': admin.email, 'password': 'private-test-password'}, client=Client())
        self.assertEqual(response.status_code, 200, response.content)

    def test_private_cv_access(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.student.resume.save('cv.pdf', SimpleUploadedFile('cv.pdf', b'%PDF-test'))
            path = self.student.resume.url
            self.assertEqual(Client().get(path).status_code, 401)
            self.assertEqual(self.client.get(path).status_code, 200)
            client = self.login('student', self.other, Client())
            self.assertEqual(client.get(path).status_code, 403)
            client = self.login('company', self.company, Client())
            self.assertEqual(client.get(path).status_code, 403)
            Application.objects.create(student=self.student, job=self.job)
            self.assertEqual(client.get(path).status_code, 200)

    def test_apply_eligibility_threshold_unchanged(self):
        with patch('core.views.AIMatchingEngine') as engine, patch('core.views.RecruitmentAgent'):
            engine.return_value.calculate_match.return_value = (59, {})
            data = {'student_id': str(self.student.pk), 'job_id': str(self.job.pk)}
            self.assertEqual(self.send('/api/apply/', data).status_code, 400)
            engine.return_value.calculate_match.return_value = (80, {})
            self.assertEqual(self.send('/api/apply/', data).status_code, 200)
            self.assertEqual(self.send('/api/apply/', data).status_code, 400)
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_applicants, 1)

    def test_company_can_post_job_without_optional_location(self):
        self.login('company', self.company)
        response = self.send('/api/job/post/', {'company_id': str(self.company.pk), 'title': 'Developer', 'description': 'Build', 'job_type': 'Remote'})
        self.assertEqual(response.status_code, 200, response.content)

    def test_missing_login_input_is_400(self):
        self.assertEqual(self.send('/api/auth/student/login/', {}, client=Client()).status_code, 400)

    def test_clearing_github_resets_account_verification(self):
        self.student.github_username = 'example'
        self.student.github_verified = True
        self.student.github_score = 80
        self.student.save()
        self.assertEqual(self.send(self.profile, {'github_username': ''}, 'put').status_code, 200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.github_verified)
        self.assertEqual(self.student.github_score, 0)

    def test_invalid_numeric_profile_data_is_rejected(self):
        self.assertEqual(self.send(self.profile, {'cgpa': 'NaN'}, 'put').status_code, 400)
        self.assertEqual(self.send(self.profile, {'projects': [{'title': 'Invalid', 'complexity': 10}]}, 'put').status_code, 400)

    def test_profile_returns_without_calling_ai(self):
        self.student.github_username = 'https://github.com/example/'
        self.student.save()
        with patch('core.views.StudentProfileView._predict_trajectory', side_effect=AssertionError('Must not run AI')):
            response = self.client.get(self.profile)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['data']['github']['username'], 'example')

    def test_dashboard_returns_without_calling_ai(self):
        with patch('core.views.StudentDashboardView._predict_trajectory', side_effect=AssertionError('Must not block dashboard')):
            response = self.client.get(f'/api/student/{self.student.pk}/dashboard/')
        self.assertEqual(response.status_code, 200, response.content)

    def test_pipeline_interview_notification_resolves_existing_route(self):
        from django.urls import resolve
        from .utils.pipeline_engine import approve_vetting_and_send_interviews
        app = Application.objects.create(student=self.student, job=self.job)
        pipeline = PipelineRun.objects.create(job=self.job, created_by=self.company, stage='vetting_review')
        PipelineCandidate.objects.create(pipeline=pipeline, application=app, sort_rank=1, stage='vetting')
        with patch('core.utils.interview_generator.generate_questions', return_value=[{'question': 'Explain your project'}]):
            approve_vetting_and_send_interviews(pipeline, [str(app.pk)], timezone.now()+timedelta(days=1))
        notice = Notification.objects.get(type='pipeline_interview')
        self.assertEqual(resolve(notice.data['interview_url']).url_name, 'candidate_interview')

    def test_empty_interview_generation_preserves_pipeline(self):
        from .utils.pipeline_engine import approve_vetting_and_send_interviews
        from .models import AIInterview
        app = Application.objects.create(student=self.student, job=self.job)
        pipeline = PipelineRun.objects.create(job=self.job, created_by=self.company, stage='vetting_review')
        candidate = PipelineCandidate.objects.create(pipeline=pipeline, application=app, sort_rank=1, stage='vetting')
        with patch('core.utils.interview_generator.generate_questions', return_value=[]):
            with self.assertRaises(RuntimeError):
                approve_vetting_and_send_interviews(pipeline, [str(app.pk)], timezone.now()+timedelta(days=1))
        candidate.refresh_from_db()
        pipeline.refresh_from_db()
        self.assertEqual(candidate.stage, 'vetting')
        self.assertEqual(pipeline.stage, 'vetting_review')
        self.assertFalse(AIInterview.objects.exists())

    def test_pipeline_handles_multiple_agent_interviews(self):
        from .models import AIInterview
        from .utils.pipeline_engine import approve_vetting_and_send_interviews
        app = Application.objects.create(student=self.student, job=self.job)
        pipeline = PipelineRun.objects.create(job=self.job, created_by=self.company, stage='vetting_review')
        PipelineCandidate.objects.create(pipeline=pipeline, application=app, sort_rank=1, stage='vetting')
        AIInterview.objects.create(application=app, token='old', questions=[{'question': 'old'}])
        latest = AIInterview.objects.create(application=app, token='latest', questions=[{'question': 'old'}], answers=[{'answer': 'old'}], status='completed', interview_score=90)
        with patch('core.utils.interview_generator.generate_questions', return_value=[{'question': 'New'}]):
            approve_vetting_and_send_interviews(pipeline, [str(app.pk)], timezone.now()+timedelta(days=1))
        latest.refresh_from_db()
        self.assertEqual(latest.status, 'pending')
        self.assertEqual(latest.answers, [])
        self.assertIsNone(latest.interview_score)
        self.assertEqual(AIInterview.objects.count(), 2)

    def test_trajectory_endpoint_uses_existing_prediction_service(self):
        with patch('core.views.StudentProfileView._predict_trajectory', return_value={'predicted_track': 'Existing calculation'}) as predictor:
            path = f'/api/student/{self.student.pk}/trajectory/'
            self.assertEqual(self.client.post(path).status_code, 200)
            self.assertEqual(self.client.post(path).status_code, 200)
            self.assertEqual(predictor.call_count, 1)

    def test_smart_apply_remains_batch_operation(self):
        with patch('core.views.AIMatchingEngine') as engine:
            engine.return_value.smart_apply.return_value = []
            response = self.send('/api/smart-apply/', {'student_id': str(self.student.pk), 'threshold': 70, 'max_applications': 5})
            self.assertEqual(response.status_code, 200, response.content)
            engine.return_value.smart_apply.assert_called_once_with(self.student, 70, 5)

    def test_all_application_paths_update_counter(self):
        app = Application.objects.create(student=self.student, job=self.job, is_auto_applied=True)
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_applicants, 1)
        app.delete()
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_applicants, 0)

    def test_gemini_initialization_failure_allows_fallback(self):
        from .utils import llm_client
        with patch.object(llm_client, '_GEMINI_API_KEY', 'test'), patch.object(llm_client, '_prefer_local', return_value=False), patch.object(llm_client.genai, 'Client', side_effect=RuntimeError('init failed')), patch.object(llm_client, '_ollama_text', return_value='fallback'):
            self.assertEqual(llm_client.llm_generate('test prompt'), 'fallback')

    def test_local_pdf_vision_receives_png_pages(self):
        from PIL import Image
        from .utils import llm_client
        buffer = io.BytesIO()
        first = Image.new('RGB', (40, 40), 'white')
        first.save(buffer, format='PDF', save_all=True, append_images=[Image.new('RGB', (40, 40), 'blue')])
        with patch.object(llm_client, '_prefer_local', return_value=True), patch.object(llm_client, '_ollama_vision', return_value='parsed') as vision:
            self.assertEqual(llm_client.llm_generate_image('prompt', buffer.getvalue(), 'application/pdf'), 'parsed')
        pages = vision.call_args.args[1]
        self.assertEqual(len(pages), 2)
        self.assertTrue(all(page.startswith(b'\x89PNG') for page in pages))
