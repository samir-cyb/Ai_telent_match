from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Student, LeaderboardEntry, StudentSkill, Project, Application
from core.utils.points import award_points


class Command(BaseCommand):
    help = 'Retroactively populate LeaderboardEntry points for all existing students.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Clear all existing leaderboard points before repopulating.',
        )

    def handle(self, *args, **options):
        if options['reset']:
            LeaderboardEntry.objects.all().delete()
            self.stdout.write(self.style.WARNING('All leaderboard entries cleared.'))

        students = Student.objects.prefetch_related('student_skills', 'projects').all()
        count = 0

        for student in students:
            with transaction.atomic():
                entry, created = LeaderboardEntry.objects.get_or_create(
                    student=student,
                    defaults={'university': student.university_id or ''}
                )
                # Keep university in sync
                if not entry.university:
                    entry.university = student.university_id or ''
                    entry.save(update_fields=['university'])

                # 1. Add skill award (one-time)
                if StudentSkill.objects.filter(student=student).exists():
                    pts = award_points(student, 'add_skill')
                    if pts:
                        self.stdout.write(f'  {student.email}: +add_skill')

                # 2. Add project award (one-time)
                if Project.objects.filter(student=student).exists():
                    pts = award_points(student, 'add_project')
                    if pts:
                        self.stdout.write(f'  {student.email}: +add_project')

                # 3. Profile completeness >= 80%
                score = float(student.profile_complete_score or 0)
                if score >= 0.80:
                    pts = award_points(student, 'profile_complete')
                    if pts:
                        self.stdout.write(f'  {student.email}: +profile_complete ({score*100:.0f}%)')

                # 4. Retroactive points for each shortlist/hire (per application)
                for app in Application.objects.filter(student=student).select_related('job'):
                    if app.status in ('shortlisted', 'hired', 'interviewed'):
                        award_points(student, 'shortlisted', unique_key=str(app.id))
                    if app.status == 'hired':
                        award_points(student, 'hired', unique_key=str(app.id))

                count += 1

        self.stdout.write(self.style.SUCCESS(f'\nDone — processed {count} students.'))
