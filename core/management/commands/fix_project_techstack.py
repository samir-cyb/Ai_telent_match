"""
Management command: fix_project_techstack

Fills in missing tech_stack for projects that have empty tech_stack
by inferring technologies from the project title and description.

Usage:
    python manage.py fix_project_techstack
    python manage.py fix_project_techstack --dry-run   # preview only
"""
from django.core.management.base import BaseCommand
from core.models import Project, Skill
from core.views import _infer_tech_from_text  # uses the same conservative inference map


class Command(BaseCommand):
    help = 'Infer and populate tech_stack for projects that currently have none'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved'))

        total = 0
        fixed = 0

        for project in Project.objects.prefetch_related('tech_stack').all():
            total += 1
            if project.tech_stack.exists():
                continue  # already has tech_stack, skip

            inferred = _infer_tech_from_text(project.title, project.description or '')
            if not inferred:
                self.stdout.write(
                    f'  [{project.student.name}] "{project.title}" — no inference possible'
                )
                continue

            self.stdout.write(
                f'  [{project.student.name}] "{project.title}" → {inferred}'
            )

            if not dry_run:
                for tech_name in inferred:
                    tech_clean = tech_name.strip().lower()
                    skill = Skill.objects.filter(name__iexact=tech_clean).first()
                    if not skill:
                        skill = Skill.objects.create(name=tech_clean, category='Uncategorized')
                    project.tech_stack.add(skill)

            fixed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone. Checked {total} projects, fixed {fixed} with empty tech_stack.'
                + (' (DRY RUN)' if dry_run else '')
            )
        )
