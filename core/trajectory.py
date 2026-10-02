import hashlib
import json

from .validation import github_handle


def display_github_username(value):
    try:
        return github_handle(value)
    except Exception:
        return ''


def trajectory_key(student):
    inputs = {
        'skills': list(student.student_skills.values_list('skill__name', 'proficiency_level')),
        'projects': list(student.projects.values_list('title', flat=True)),
        'experiences': list(student.experiences.values('role', 'company_name', 'start_date', 'end_date')),
        'cgpa': student.cgpa, 'department': student.department,
        'jobs': list(student.applications.values_list('job_id', flat=True)),
    }
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
    return f'trajectory:{student.pk}:{digest}'
