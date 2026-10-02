import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from core.models import Admin


class Command(BaseCommand):
    help = 'Create a platform admin with a private hashed password.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--super-admin', action='store_true')

    def handle(self, *args, **options):
        email = options['email'].strip()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError('Use a valid email address.') from exc
        if Admin.objects.filter(email=email).exists():
            raise CommandError('This admin already exists; its password was not changed.')
        password = os.environ.get('PLATFORM_ADMIN_PASSWORD') or getpass.getpass('New platform admin password: ')
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        admin = Admin(email=email, is_super_admin=options['super_admin'])
        admin.set_password(password)
        admin.save()
        self.stdout.write(self.style.SUCCESS('Platform admin created.'))
