from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Job


class Command(BaseCommand):
    help = 'Preview historical applicant counter corrections; --apply writes derived counts.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        changed = 0
        with transaction.atomic():
            for job in Job.objects.select_for_update().all().iterator():
                actual = job.applications.count()
                if job.total_applicants != actual:
                    self.stdout.write(f'{job.pk}: {job.total_applicants} -> {actual}')
                    changed += 1
                    if options['apply']:
                        job.total_applicants = actual
                        job.save(update_fields=['total_applicants'])
        self.stdout.write(f'{changed} counters ' + ('corrected.' if options['apply'] else 'would be corrected; pass --apply after review.'))
