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
    # ADD THIS NEW ENDPOINT for explicit updates:
    path('student/<uuid:student_id>/profile/update/', views.StudentProfileView.as_view(), name='update_student_profile'),
    path('student/<uuid:student_id>/dashboard/', views.StudentDashboardView.as_view(), name='student_dashboard'),
    path('student/<uuid:student_id>/matches/', views.StudentMatchesView.as_view(), name='student_matches'),
    
    # ADD THESE TWO NEW ENDPOINTS HERE
    path('student/<uuid:student_id>/skills/', views.AddSkillView.as_view(), name='add_skill'),
    path('student/<uuid:student_id>/experience/', views.AddExperienceView.as_view(), name='add_experience'),
    path('student/<uuid:student_id>/preferences/', views.UpdatePreferencesView.as_view(), name='update_preferences'),
    path('student/<uuid:student_id>/applications/', views.StudentApplicationsView.as_view(), name='student_applications'),
    
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
    path('company/<uuid:company_id>/weights/', views.CompanyWeightsView.as_view(), name='company_weights'),
    
    # Admin endpoints
    path('admin/analytics/', views.AdminAnalyticsView.as_view(), name='admin_analytics'),
    path('admin/fraud-flags/', views.FraudFlagsListView.as_view(), name='fraud_flags_list'),
    path('admin/resolve-fraud/', views.ResolveFraudFlagView.as_view(), name='resolve_fraud'),
    # Admin Auth endpoints - ADD THESE
    path('auth/admin/login/', views.AdminLoginView.as_view(), name='admin_login'),
    path('auth/admin/logout/', views.AdminLogoutView.as_view(), name='admin_logout'),
    path('admin/add/', views.AddAdminView.as_view(), name='add_admin'),
    path('admin/list/', views.ListAdminsView.as_view(), name='list_admins'),
    
    # Notifications & Scheduling
    path('notifications/<uuid:user_id>/<str:user_type>/', views.NotificationsView.as_view(), name='notifications'),
    path('interview/schedule/', views.ScheduleInterviewView.as_view(), name='schedule_interview'),
]