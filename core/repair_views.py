from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from .models import Application, Project, Skill, Student
from .permissions import principal
from .trajectory import trajectory_key
from .validation import github_handle


class TrajectoryView(View):
    def post(self, request, student_id):
        from .views import StudentProfileView
        student = get_object_or_404(Student, pk=student_id)
        key = trajectory_key(student)
        prediction = cache.get(key)
        if prediction is None:
            skills = list(student.student_skills.values_list('skill__name', flat=True))
            prediction = StudentProfileView()._predict_trajectory(skills, student.projects.count(), student=student)
            cache.set(key, prediction, 900)
        return JsonResponse({'status': 'success', 'data': prediction})


class GitHubSyncView(View):
    def post(self, request, student_id):
        from .utils.github_scraper import GitHubValidator
        student = get_object_or_404(Student, pk=student_id)
        username = github_handle(student.github_username)
        if not username:
            return JsonResponse({'status': 'error', 'message': 'Save a GitHub username first.'}, status=400)
        result = GitHubValidator().validate_student_github(username)
        if not result.get('valid'):
            return JsonResponse({'status': 'error', 'message': result.get('error', 'GitHub is unavailable.')}, status=502)
        imported = updated = skipped = 0
        with transaction.atomic():
            student = Student.objects.select_for_update().get(pk=student.pk)
            if github_handle(student.github_username) != username:
                return JsonResponse({'status': 'error', 'message': 'GitHub account changed. Refresh and retry.'}, status=409)
            for repo in result.get('verified_projects', []):
                repo_id = repo.get('id')
                url = repo.get('url', '')
                project = student.projects.filter(github_repo_id=repo_id).first() if repo_id else None
                project = project or student.projects.filter(github_url=url).first()
                if project is None and student.projects.filter(title__iexact=repo['name']).exists():
                    skipped += 1
                    continue
                if project is None:
                    project = Project(student=student, title=repo['name'], description=repo.get('description') or '', source='github')
                    imported += 1
                else:
                    updated += 1
                    if project.source == 'github':
                        project.description = repo.get('description') or project.description
                project.github_repo_id = repo_id
                project.github_url = url
                project.verified = True
                project.save()
                if repo.get('language'):
                    skill = Skill.objects.filter(name__iexact=repo['language']).first()
                    if skill is None:
                        skill = Skill.objects.create(name=repo['language'].lower(), category='Uncategorized')
                    project.tech_stack.add(skill)
            student.github_username = username
            student.github_verified = True
            student.github_score = result['score']
            student.save(update_fields=['github_username', 'github_verified', 'github_score'])
            student.calculate_trust_score()
        return JsonResponse({'status': 'success', 'imported': imported, 'updated': updated, 'skipped': skipped})


def private_document(request, filename):
    role, uid = principal(request)
    if not role:
        return JsonResponse({'status': 'error', 'message': 'Please log in.'}, status=401)
    student = get_object_or_404(Student, Q(resume=filename) | Q(linkedin_pdf=filename))
    allowed = role == 'admin' or role == 'student' and str(student.pk) == uid
    if role == 'company':
        allowed = Application.objects.filter(student=student, job__company_id=uid).exists()
    if not allowed:
        return JsonResponse({'status': 'error', 'message': 'Document access denied.'}, status=403)
    field = student.resume if student.resume.name == filename else student.linkedin_pdf
    if not field.storage.exists(field.name):
        return JsonResponse({'status': 'error', 'message': 'Document file is unavailable.'}, status=404)
    response = FileResponse(field.open('rb'), as_attachment=True)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
