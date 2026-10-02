from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, F

from core.models import Application, Job


class Command(BaseCommand):
    help = 'Read-only local configuration and database checks; does not probe external services.'

    def handle(self, *args, **options):
        call_command('check', stdout=self.stdout)
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        self.stdout.write('Database connection: OK')
        duplicates = Application.objects.values('student_id', 'job_id').annotate(n=Count('pk')).filter(n__gt=1).count()
        stale = Job.objects.annotate(actual=Count('applications')).exclude(total_applicants=F('actual')).count()
        self.stdout.write(f'Duplicate application pairs: {duplicates}; outdated applicant counters: {stale}')
        self.stdout.write('AI preference: ' + ('Ollama first' if settings.LLM_PREFER_LOCAL else 'Gemini with Ollama fallback'))
        self.stdout.write('Gemini key: ' + ('configured' if settings.GEMINI_API_KEY else 'not configured'))
        self.stdout.write('GitHub token: ' + ('configured' if settings.GITHUB_TOKEN else 'not configured (public API rate limits apply)'))
        self.stdout.write('Sandbox URL: configured; auth ' + ('configured' if settings.JUDGE0_AUTH_TOKEN else 'not configured'))
        self.stdout.write('Email backend: ' + settings.EMAIL_BACKEND)
        self.stdout.write('Configuration checks do not verify live AI, SMTP, Redis or Judge0 availability.')
        if duplicates:
            raise CommandError('Back up and reconcile duplicate applications before applying migration 0022; no records were changed.')
