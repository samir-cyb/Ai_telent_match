from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from vetting.views import SubmissionDetailView
from core.views import (
    InterviewSlotAvailabilityView, landing_page, about_us, services,
    student_login, student_register, student_dashboard, student_profile, student_job_detail, student_jobs,
    company_login, company_register, company_dashboard, company_post_job, company_applicants,
    applicant_documents, company_ai_agent, company_agent_run_detail,
    company_interview_result,
    CandidateInterviewPageView, SubmitAnswerView, InterviewDonePageView,
    admin_dashboard, admin_analytics, admin_fraud_review, StudentLogoutView, CompanyLogoutView, admin_login_page, ApplicationsListView,
    student_career_advisor_page, company_skill_heatmap, student_leaderboard,
    student_skill_heatmap, company_leaderboard,
    SendJobOfferView, StudentQuickPreviewView, LeaderboardShortlistView,
    company_pipeline_page,
)
from core.repair_views import private_document

urlpatterns = [
    path('media/<path:filename>', private_document, name='private_document'),
    path('', landing_page, name='landing'),
    path('about/', about_us, name='about'),
    path('services/', services, name='services'),
    
    # Authentication
    path('student/login/', student_login, name='student_login'),
    path('student/register/', student_register, name='student_register'),
    path('company/login/', company_login, name='company_login'),
    path('company/register/', company_register, name='company_register'),
    
    # Student
    path('student/dashboard/', student_dashboard, name='student_dashboard'),
    path('student/profile/', student_profile, name='student_profile'),
    path('student/job-detail/', student_job_detail, name='student_job_detail'),
    path('student/jobs/', student_jobs, name='student_jobs'),
    path('api/auth/student/logout/', StudentLogoutView.as_view(), name='student_logout'),
    path('student/career-advisor/', student_career_advisor_page, name='career_advisor'),
    
    # Company
    path('company/dashboard/', company_dashboard, name='company_dashboard'),
    path('company/post-job/', company_post_job, name='company_post_job'),
    path('company/applicants/', company_applicants, name='company_applicants'),
    path('company/skill-heatmap/', company_skill_heatmap, name='company_skill_heatmap'),
    path('company/applicant/<uuid:application_id>/documents/', applicant_documents, name='applicant_documents'),
    path('company/ai-agent/', company_ai_agent, name='company_ai_agent'),
    path('company/agent-run/<uuid:run_id>/', company_agent_run_detail, name='company_agent_run_detail'),
    path('company/interview/<uuid:interview_id>/result/', company_interview_result, name='company_interview_result'),

    # Candidate interview (token-based)
    path('interview/<str:token>/',        CandidateInterviewPageView.as_view(), name='candidate_interview'),
    path('interview/<str:token>/submit/', SubmitAnswerView.as_view(), name='submit_answer'),
    path('interview/<str:token>/done/',   InterviewDonePageView.as_view(), name='interview_done'),
    path('api/auth/company/logout/', CompanyLogoutView.as_view(), name='company_logout'),
    
    # Admin
    path('admin/dashboard/', admin_dashboard, name='admin_dashboard'),
    path('admin/analytics/', admin_analytics, name='admin_analytics'),
    path('admin/fraud-review/', admin_fraud_review, name='admin_fraud_review'),
    path('admin/login/', admin_login_page, name='admin_login_page'),
    path('admin/', admin.site.urls),
    path('applications/', ApplicationsListView.as_view()),
    path('job/<uuid:job_id>/slot-availability/', InterviewSlotAvailabilityView.as_view()),
    path('student/leaderboard/', student_leaderboard, name='student_leaderboard'),
    path('student/skill-heatmap/', student_skill_heatmap, name='student_skill_heatmap'),
    path('company/leaderboard/', company_leaderboard, name='company_leaderboard'),
    path('api/leaderboard/send-offer/', SendJobOfferView.as_view(), name='send_job_offer'),
    path('api/leaderboard/shortlist/', LeaderboardShortlistView.as_view(), name='leaderboard_shortlist'),
    path('api/student/<uuid:student_id>/quick-preview/', StudentQuickPreviewView.as_view(), name='student_quick_preview'),
    # Auto Pipeline page
    path('company/pipeline/<uuid:pipeline_id>/', company_pipeline_page, name='company_pipeline'),
    # API
    path('api/', include('core.urls')),
    
    #vetting
    path('vetting/', include('vetting.urls')),  # ADD THIS LINE
    path('vetting/api/', include('vetting.urls')),
    path('vetting/submission/<uuid:submission_id>/', SubmissionDetailView.as_view(), name='submission_detail'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    # CV documents are served only by the authorized private document endpoint.
from core.permissions import protect_urlpatterns
urlpatterns = protect_urlpatterns(urlpatterns)
