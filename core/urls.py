from django.urls import path
from . import views

urlpatterns = [
    # Auth endpoints
    path('auth/student/login/', views.StudentLoginView.as_view(), name='api_student_login'),
    path('auth/student/register/', views.StudentRegisterView.as_view(), name='api_student_register'),
    path('auth/company/login/', views.CompanyLoginView.as_view(), name='api_company_login'),
    path('auth/company/register/', views.CompanyRegisterView.as_view(), name='api_company_register'),
    
    # Student endpoints
    path('student/<uuid:student_id>/profile/', views.StudentProfileView.as_view(), name='student_profile'),
    path('student/create/', views.StudentProfileView.as_view(), name='create_student'),
    path('student/<uuid:student_id>/dashboard/', views.StudentDashboardView.as_view(), name='student_dashboard'),
    path('student/<uuid:student_id>/matches/', views.StudentMatchesView.as_view(), name='student_matches'),
    path('analyze-match/', views.AnalyzeMatchView.as_view(), name='analyze_match'),
    path('smart-apply/', views.SmartApplyView.as_view(), name='smart_apply'),
    path('jobs/', views.JobsListView.as_view(), name='jobs_list'),
    path('apply/', views.ApplyJobView.as_view(), name='apply_job'),
    
    # Company endpoints
    path('company/<uuid:company_id>/dashboard/', views.CompanyDashboardView.as_view(), name='company_dashboard'),
    path('job/post/', views.PostJobView.as_view(), name='post_job'),
    path('job/shortlist/', views.ShortlistCandidatesView.as_view(), name='shortlist_candidates'),
    path('application/hire/', views.HireCandidateView.as_view(), name='hire_candidate'),
    path('applications/', views.ApplicationsListView.as_view(), name='applications_list'),
    path('application/update/', views.UpdateApplicationView.as_view(), name='update_application'),
    
    # Admin endpoints
    path('admin/analytics/', views.AdminAnalyticsView.as_view(), name='admin_analytics'),
    path('admin/fraud-flags/', views.FraudFlagsListView.as_view(), name='fraud_flags_list'),
    path('admin/resolve-fraud/', views.ResolveFraudFlagView.as_view(), name='resolve_fraud'),
    
    # Notifications & Scheduling
    path('notifications/<uuid:user_id>/<str:user_type>/', views.NotificationsView.as_view(), name='notifications'),
    path('interview/schedule/', views.ScheduleInterviewView.as_view(), name='schedule_interview'),
]