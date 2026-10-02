import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from core.models import Application, Company, Job, Student
from .models import CodeSubmission, VettingChallenge, VettingResult, VettingSession


class AssessmentRepairTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(name='Student', email='vet@example.test', department='CSE', university_id='S1')
        self.company = Company.objects.create(name='Company', email='vetco@example.test', industry='Software', size='Startup')
        self.job = Job.objects.create(company=self.company, title='Developer', description='Build', job_type='Remote')
        self.application = Application.objects.create(student=self.student, job=self.job)
        self.challenge = VettingChallenge.objects.create(job=self.job, title='Quiz', description='Answer', starter_code='', test_cases=[], assessment_type='mcq_written', mcq_questions=[
            {'id': 1, 'type': 'mcq', 'question': 'Question', 'options': ['A. First', 'B. Second'], 'correct_answer': 'SECRET_ANSWER', 'explanation': 'SECRET_EXPLANATION', 'points': 10},
            {'id': 2, 'type': 'written', 'question': 'Explain', 'grading_rubric': 'SECRET_RUBRIC', 'word_limit': 350, 'points': 20},
        ])
        self.session = VettingSession.objects.create(challenge=self.challenge, student=self.student, application=self.application, token_expires_at=timezone.now()+timedelta(days=2), window_start=timezone.now()-timedelta(hours=1), window_end=timezone.now()+timedelta(hours=1))
        self.url = f'/vetting/test/{self.session.access_token}/'

    def post(self, suffix, data):
        return self.client.post(f'/vetting/api/test/{self.session.access_token}/{suffix}/', json.dumps(data), content_type='application/json')

    def test_quiz_html_hides_solutions_and_preserves_points_word_limit(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for secret in ('SECRET_ANSWER', 'SECRET_EXPLANATION', 'SECRET_RUBRIC'):
            self.assertNotContains(response, secret)
        questions = json.loads(response.context['questions_json'])
        self.assertEqual(questions[0]['points'], 10)
        self.assertEqual(questions[1]['word_limit'], 350)

    def test_refresh_resumes_same_session(self):
        self.client.get(self.url)
        self.session.refresh_from_db()
        started = self.session.started_at
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Assessment window has closed.')
        self.session.refresh_from_db()
        self.assertEqual(self.session.started_at, started)

    def test_timer_does_not_wrap_after_24_hours(self):
        self.session.started_at = timezone.now()-timedelta(days=1, minutes=1)
        self.assertFalse(self.session.has_time_remaining())
        self.assertEqual(self.session.get_time_remaining_seconds(), 0)

    def test_expired_in_progress_page_has_clear_response(self):
        self.session.started_at = timezone.now()-timedelta(hours=2)
        self.session.status = 'in_progress'
        self.session.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 410)
        self.assertContains(response, 'Assessment time has expired.', status_code=410)

    def test_expiry_uses_existing_saved_code_submission_workflow(self):
        self.challenge.assessment_type = 'coding'
        self.challenge.test_cases = [{'input': '', 'expected': '1'}]
        self.challenge.save()
        self.session.started_at = timezone.now()-timedelta(hours=2)
        self.session.status = 'in_progress'
        self.session.save()
        CodeSubmission.objects.create(session=self.session, code='print(1)', language='python')
        grading = {'layer1_test_score': 100, 'layer2_static_score': 80, 'layer3_ai_score': 80,
                   'final_score': 90, 'passed': True, 'details': {}}
        with patch('vetting.views.CodeExecutor.run_test_cases', return_value={'passed': 1, 'total': 1, 'score': 100, 'details': []}) as runner, patch('vetting.views.CodeGrader.grade', return_value=grading):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(VettingResult.objects.exists())
        self.assertEqual(runner.call_args.args[0], 'print(1)')

    def test_expired_token_execution_rejected(self):
        self.session.token_expires_at = timezone.now()-timedelta(seconds=1)
        self.session.save()
        self.assertEqual(self.post('execute', {'code': 'print(1)'}).status_code, 403)

    def test_anti_cheat_termination_is_persisted(self):
        self.challenge.assessment_type = 'coding'
        self.challenge.save()
        self.session.status = 'in_progress'
        self.session.started_at = timezone.now()
        self.session.save()
        response = self.post('submit', {'code': 'print(1)', 'tab_switches': 5})
        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'cheating_detected')

    def test_sandbox_outage_preserves_in_progress_session_and_results(self):
        from .services.code_executor import SandboxUnavailable
        self.challenge.assessment_type = 'coding'
        self.challenge.test_cases = [{'input': '', 'expected': '1'}]
        self.challenge.save()
        self.session.status = 'in_progress'
        self.session.started_at = timezone.now()
        self.session.save()
        with patch('vetting.views.CodeExecutor.run_test_cases', side_effect=SandboxUnavailable('Sandbox unavailable')):
            response = self.post('submit', {'code': 'print(1)'})
        self.assertEqual(response.status_code, 503)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'in_progress')
        self.assertFalse(VettingResult.objects.exists())

    def test_submission_detail_uses_result_id_and_checks_owner(self):
        result = VettingResult.objects.create(session=self.session, application=self.application, final_score=80)
        CodeSubmission.objects.create(session=self.session, code='print(1)', language='python', is_final=True)
        path = f'/vetting/submission/{result.pk}/'
        self.assertEqual(self.client.get(path).status_code, 401)
        session = self.client.session
        session['company_id'] = str(self.company.pk)
        session['user_type'] = 'company'
        session.save()
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['code'], 'print(1)')


class SubmissionTransactionTests(TransactionTestCase):
    setUp = AssessmentRepairTests.setUp
    post = AssessmentRepairTests.post

    def test_slow_grading_runs_without_database_transaction(self):
        from django.db import connection
        self.challenge.assessment_type = 'coding'
        self.challenge.test_cases = [{'input': '', 'expected': '1'}]
        self.challenge.save()
        self.session.status = 'in_progress'
        self.session.started_at = timezone.now()
        self.session.save()
        def run(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            return {'passed': 1, 'total': 1, 'score': 100, 'details': []}
        grading = {'layer1_test_score': 100, 'layer2_static_score': 80, 'layer3_ai_score': 80,
                   'final_score': 90, 'passed': True, 'details': {}}
        with patch('vetting.views.CodeExecutor.run_test_cases', side_effect=run), patch('vetting.views.CodeGrader.grade', return_value=grading):
            response = self.post('submit', {'code': 'print(1)'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(VettingResult.objects.count(), 1)
