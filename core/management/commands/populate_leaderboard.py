from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Student, LeaderboardEntry, StudentSkill, Project
from core.utils.points import award_points

class Command(BaseCommand):
    help = 'Populate LeaderboardEntry with points for existing students based on their current profile'

    def handle(self, *args, **options):
        self.stdout.write("Starting retroactive point assignment...")
        students = Student.objects.all()
        count = 0

        for student in students:
            with transaction.atomic():
                entry, created = LeaderboardEntry.objects.get_or_create(student=student)
                # Set university if not set
                if not entry.university:
                    entry.university = student.department or 'Unknown'
                    entry.save()

                # Award for first skill
                if StudentSkill.objects.filter(student=student).exists():
                    if 'add_skill' not in entry.awarded_actions:
                        award_points(student, 'add_skill')
                        self.stdout.write(f"  {student.email}: awarded 'add_skill'")

                # Award for first project
                if Project.objects.filter(student=student).exists():
                    if 'add_project' not in entry.awarded_actions:
                        award_points(student, 'add_project')
                        self.stdout.write(f"  {student.email}: awarded 'add_project'")

                # Award for profile completion (>= 99%)
                if student.profile_complete_score and float(student.profile_complete_score) >= 0.99:
                    if 'profile_complete' not in entry.awarded_actions:
                        award_points(student, 'profile_complete')
                        self.stdout.write(f"  {student.email}: awarded 'profile_complete'")

                # Optional: award for passed assessments
                # You can add logic here if you have vetting results with passed=True

                count += 1

        self.stdout.write(self.style.SUCCESS(f"Done! Processed {count} students."))