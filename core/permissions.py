"""Session and ownership checks shared by the existing role APIs.

Token assessment/interview routes retain their bearer token workflow. They
also reject a different signed-in student. New class routes are denied until
their policy is declared here.
"""
import json
from functools import wraps

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_protect

from .models import Admin, Application, Company, Job, Student
from .validation import validate_payload, validate_upload

PUBLIC = set('StudentLoginView StudentRegisterView CompanyLoginView CompanyRegisterView AdminLoginView JobsListView'.split())
TOKEN = set('CandidateInterviewPageView SubmitAnswerView InterviewDonePageView ReportInterviewCheatingView TestInterfaceView ExecuteCodeView SubmitTestView SubmitQuizView'.split())
STUDENT = set('StudentProfileView StudentDashboardView StudentMatchesView AddSkillView AddExperienceView UpdatePreferencesView StudentApplicationsView ApplicationStatusDetailView StudentAIInterviewsView CareerAdvisorChatView AdvisorSessionListView AdvisorSessionDetailView UploadResumeView LinkedInPDFUploadView SmartJobRecommendationsView SmartApplyView ApplyJobView StudentLogoutView StudentPendingAssessmentsView GitHubSyncView TrajectoryView'.split())
COMPANY = set('CompanyDashboardView PostJobView ShortlistCandidatesView HireCandidateView ApplicationsListView UpdateApplicationView CompanyWeightsView WeightAgentDataView RunRecruitmentAgentView AgentRunsListView AgentRunDetailAPIView GenerateInterviewView AIInterviewAnalyzeView DeleteJobView InterviewSlotView ScheduleInterviewView AIEffectivenessView SkillDemandHeatmapView CreatePipelineView PipelineStatusView ApproveSortView ApproveVettingView CancelPipelineView JobPipelinesView SendJobOfferView StudentQuickPreviewView LeaderboardShortlistView CompanyLogoutView CreateChallengeView PreviewChallengeView GenerateAssessmentTokenView CompanyVettingDashboardView'.split())
ADMIN = set('AdminAnalyticsView FraudFlagsListView ResolveFraudFlagView AddAdminView AdminLogoutView ListAdminsView DebugStudentScoresView'.split())
SHARED = set('NotificationsView MarkAllNotificationsReadView InterviewSlotAvailabilityView AvailableSlotsView LeaderboardView PlatformSkillHeatmapView AnalyzeMatchView VettingResultDetailView SubmissionDetailView'.split())
# Assessment submission views manage their own short transactions around grading.
ATOMIC = set('StudentProfileView StudentRegisterView CompanyRegisterView PostJobView AddSkillView AddExperienceView UpdatePreferencesView ApplyJobView SmartApplyView UpdateApplicationView ShortlistCandidatesView HireCandidateView LeaderboardShortlistView CreatePipelineView PipelineStatusView ApproveSortView ApproveVettingView CancelPipelineView LinkedInPDFUploadView'.split())


def principal(request):
    role = request.session.get('user_type')
    # Older sessions did not always set user_type.
    if role not in ('student', 'company', 'admin'):
        roles = [r for r in ('student', 'company', 'admin') if request.session.get(r + '_id')]
        role = roles[0] if len(roles) == 1 else None
    model = {'student': Student, 'company': Company, 'admin': Admin}.get(role)
    uid = request.session.get(str(role) + '_id')
    try:
        if model and uid and model.objects.filter(pk=uid).exists():
            return role, str(uid)
    except (ValidationError, ValueError):
        pass
    return None, None


def error(message, status):
    return JsonResponse({'status': 'error', 'message': message}, status=status)


def ownership(request, name, args):
    role, uid = principal(request)
    if name in PUBLIC or (name == 'StudentProfileView' and request.method == 'POST' and not args.get('student_id')):
        return None
    if name in TOKEN:
        token = args.get('token')
        if token and role:
            if name in ('TestInterfaceView', 'ExecuteCodeView', 'SubmitTestView', 'SubmitQuizView'):
                from vetting.models import VettingSession
                session = get_object_or_404(VettingSession, access_token=token)
                if not session.is_token_valid():
                    return error('Assessment link has expired.', 403)
                student_id = session.student_id
            else:
                from core.models import AIInterview
                interview = get_object_or_404(AIInterview, token=token)
                student_id = interview.application.student_id
            if role != 'student' or str(student_id) != uid:
                return error('This link belongs to another account.', 403)
        # All execution/submission token requests must enforce expiry, including anonymous ones.
        if token and name in ('ExecuteCodeView', 'SubmitTestView', 'SubmitQuizView'):
            from vetting.models import VettingSession
            session = get_object_or_404(VettingSession, access_token=token)
            if not session.is_token_valid():
                return error('Assessment link has expired.', 403)
        return None
    allowed = ({'student'} if name in STUDENT else {'company'} if name in COMPANY else {'admin'} if name in ADMIN else {'student', 'company', 'admin'} if name in SHARED else set())
    if not role:
        return error('Please log in again.', 401)
    if role not in allowed:
        return error('This operation is not available to this account.', 403)
    if name == 'StudentProfileView' and request.method == 'POST':
        return error('Use PUT to update a profile.', 405)
    for key in ('student_id', 'company_id'):
        if args.get(key) and role == key[:-3] and str(args[key]) != uid:
            return error('You cannot access another account.', 403)
    if name in ('NotificationsView', 'MarkAllNotificationsReadView'):
        if str(args.get('user_id')) != uid or args.get('user_type', role) != role:
            return error('You cannot access another account notifications.', 403)
    job = None
    if args.get('job_id'):
        job = get_object_or_404(Job, pk=args['job_id'])
    app = None
    if args.get('application_id'):
        app = get_object_or_404(Application.objects.select_related('job'), pk=args['application_id'])
        job = app.job
    if args.get('run_id'):
        from .models import RecruitmentAgentRun
        run = get_object_or_404(RecruitmentAgentRun.objects.select_related('application__job'), pk=args['run_id'])
        job = run.application.job
    if args.get('interview_id'):
        from .models import AIInterview
        interview = get_object_or_404(AIInterview.objects.select_related('application__job'), pk=args['interview_id'])
        job = interview.application.job
    if args.get('pipeline_id'):
        from .models import PipelineRun
        job = get_object_or_404(PipelineRun.objects.select_related('job'), pk=args['pipeline_id']).job
    if name in ('VettingResultDetailView', 'SubmissionDetailView'):
        from vetting.models import VettingResult
        result = get_object_or_404(VettingResult.objects.select_related('application__job'), pk=args.get('result_id') or args.get('submission_id'))
        app, job = result.application, result.application.job
    if role == 'student' and app and str(app.student_id) != uid:
        return error('This application belongs to another student.', 403)
    if role == 'company' and job and str(job.company_id) != uid:
        return error('This job belongs to another company.', 403)
    if name == 'AnalyzeMatchView' and role == 'student' and str(args.get('student_id')) != uid:
        return error('You cannot analyze another student.', 403)
    return None


def protect(view):
    if getattr(view, '_api_protected', False) or not hasattr(view, 'view_class'):
        return view
    name = view.view_class.__name__

    @wraps(view)
    def guarded(request, *positional, **kwargs):
        try:
            data = {}
            if 'application/json' in (request.content_type or '') and request.body:
                data = json.loads(request.body)
                if not isinstance(data, dict):
                    return error('JSON body must be an object.', 400)
            args = {**request.GET.dict(), **request.POST.dict(), **data, **kwargs}
            denied = ownership(request, name, args)
            if denied is not None:
                return denied
            validate_payload(name, request.method, data)
            if data:
                request._body = json.dumps(data).encode('utf-8')
            for field, upload in request.FILES.items():
                validate_upload(upload, pdf_only=field == 'linkedin_pdf')
            if name not in ATOMIC or request.method == 'GET' and name != 'PipelineStatusView':
                return view(request, *positional, **kwargs)
            with transaction.atomic():
                role, uid = principal(request)
                if role == 'student':
                    Student.objects.select_for_update().get(pk=uid)
                elif role == 'company':
                    Company.objects.select_for_update().get(pk=uid)
                response = view(request, *positional, **kwargs)
                if response.status_code >= 400:
                    transaction.set_rollback(True)
                return response
        except Http404:
            return error('Requested record was not found.', 404)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            message = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            return error(message or 'Invalid request.', 400)
        except IntegrityError:
            return error('This record already exists or conflicts with another update.', 409)
        except RuntimeError:
            return error('A required service is unavailable. Please retry after checking its configuration.', 503)

    guarded.csrf_exempt = False
    wrapped = csrf_protect(guarded)
    wrapped.csrf_exempt = False
    wrapped._api_protected = True
    return wrapped


def protect_urlpatterns(patterns):
    for pattern in patterns:
        if hasattr(pattern, 'callback'):
            pattern.callback = protect(pattern.callback)
    return patterns
