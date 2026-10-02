"""Validate API input before a handler can mutate stored profile data."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError


def github_handle(value):
    value = str(value or '').strip().rstrip('/')
    if not value:
        return ''
    if value.startswith(('github.com/', 'www.github.com/')):
        value = 'https://' + value
    if '://' in value:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('github.com', 'www.github.com'):
            raise ValidationError('Use a GitHub username or GitHub profile URL.')
        value = parsed.path.strip('/')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', value) or '--' in value:
        raise ValidationError('Invalid GitHub username.')
    return value


def valid_date(value):
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValidationError('Dates must use YYYY-MM-DD.')


def validate_payload(name, method, data):
    if method not in ('POST', 'PUT', 'PATCH'):
        return
    required = {
        'StudentLoginView': ('email', 'password'), 'CompanyLoginView': ('email', 'password'),
        'AdminLoginView': ('email', 'password'), 'StudentRegisterView': ('name', 'email', 'password'),
        'CompanyRegisterView': ('name', 'email', 'password'),
        'AddSkillView': ('skill_name', 'proficiency_level'),
        'AddExperienceView': ('company_name', 'role', 'start_date'),
        'ApplyJobView': ('student_id', 'job_id'), 'SmartApplyView': ('student_id',),
        'AnalyzeMatchView': ('student_id', 'job_id'),
        'PostJobView': ('company_id', 'title', 'description', 'job_type'),
        'UpdateApplicationView': ('application_id', 'status'), 'HireCandidateView': ('application_id',),
        'ShortlistCandidatesView': ('job_id',), 'CreatePipelineView': ('job_id',),
    }
    if name == 'StudentProfileView' and method == 'POST':
        fields = ('name', 'email', 'password')
    else:
        fields = required.get(name, ())
    for field in fields:
        if data.get(field) in (None, ''):
            raise ValidationError(f'{field} is required.')
    if 'github_username' in data:
        data['github_username'] = github_handle(data['github_username'])
    if 'preferences' in data and not isinstance(data['preferences'], dict):
        raise ValidationError('preferences must be an object.')
    if 'cgpa' in data and data['cgpa'] not in (None, ''):
        try:
            cgpa = Decimal(str(data['cgpa']))
            if not cgpa.is_finite() or not 0 <= cgpa <= 4:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ValidationError('CGPA must be between 0 and 4.')
    if 'graduation_date' in data:
        valid_date(data['graduation_date'])
    for field in ('linkedin_url', 'portfolio_url', 'behance_url'):
        if data.get(field) and urlsplit(str(data[field])).scheme not in ('https', 'http'):
            raise ValidationError(f'{field} must use HTTP or HTTPS.')
    for field in ('skills', 'projects', 'experiences', 'certifications', 'eca_activities', 'research_papers'):
        if field in data and (not isinstance(data[field], list) or any(not isinstance(x, dict) for x in data[field])):
            raise ValidationError(f'{field} must be a list of objects.')
    experiences = data.get('experiences', [])
    if name == 'AddExperienceView':
        experiences = [data]
    for item in experiences:
        start = valid_date(item.get('start_date'))
        end = valid_date(item.get('end_date'))
        if not start or (end and end < start):
            raise ValidationError('Experience requires a valid start date and an end date after it.')
    for item in data.get('projects', []):
        complexity = item.get('complexity') or 3
        if isinstance(complexity, bool) or int(complexity) != float(complexity) or not 1 <= int(complexity) <= 5:
            raise ValidationError('Project complexity must be an integer from 1 to 5.')
        url = str(item.get('github_url') or '').strip()

        if url.startswith(('github.com/', 'www.github.com/')):
            url = 'https://' + url

        if url and urlsplit(url).scheme not in ('http', 'https'):
            title = item.get('title') or 'Untitled'
            raise ValidationError(
                f'Project "{title}": GitHub URL must start with http:// or https://.'
            )

        item['github_url'] = url or None
    if name == 'UpdateApplicationView':
        from core.models import Application
        if data.get('status') not in dict(Application.STATUS_CHOICES):
            raise ValidationError('Invalid application status.')
    if name == 'SmartApplyView':
        if not 0 <= float(data.get('threshold', 70)) <= 100 or int(data.get('max_applications', 5)) < 1:
            raise ValidationError('Invalid smart apply threshold or application count.')


def validate_upload(upload, pdf_only=False):
    if upload.size > settings.MAX_PROFILE_UPLOAD_BYTES:
        raise ValidationError('Upload must be at most 10 MB.')
    signature = upload.read(8)
    upload.seek(0)
    pdf = signature.startswith(b'%PDF-')
    image = signature.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'))
    if not pdf and (pdf_only or not image):
        raise ValidationError('Upload a PDF' + ('.' if pdf_only else ', PNG or JPEG file.'))
