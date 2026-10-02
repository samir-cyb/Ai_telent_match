import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.models import Admin


class Command(BaseCommand):
    help = 'Rotate an existing platform admin password without changing its role.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)

    def handle(self, *args, **options):
        admin = Admin.objects.filter(email=options['email']).first()
        if admin is None:
            raise CommandError('Platform admin not found.')
        password = getpass.getpass('New platform admin password: ')
        if password != getpass.getpass('Confirm password: '):
            raise CommandError('Passwords did not match; no change was saved.')
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        admin.set_password(password)
        admin.save(update_fields=['password'])
        # Revoke server sessions for this account, including sessions minted
        # through the removed fixed credential bypass.
        from django.contrib.sessions.models import Session
        for session in Session.objects.all().iterator():
            if str(session.get_decoded().get('admin_id', '')) == str(admin.pk):
                session.delete()
        self.stdout.write(self.style.SUCCESS('Admin password changed; existing sessions revoked.'))
