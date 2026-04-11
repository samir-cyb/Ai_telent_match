from django.urls import path
from . import views

urlpatterns = [
    # Company routes - ALL should start with 'api/'
    path('api/challenge/create/', views.CreateChallengeView.as_view(), name='create_challenge'),
    path('api/challenge/token/', views.GenerateAssessmentTokenView.as_view(), name='generate_token'),
    path('job/<uuid:job_id>/vetting-dashboard/', views.CompanyVettingDashboardView.as_view(), name='vetting_dashboard'),
    
    # Student test routes
    path('test/<str:token>/', views.TestInterfaceView.as_view(), name='take_test'),
    path('api/test/<str:token>/execute/', views.ExecuteCodeView.as_view(), name='execute_code'),
    path('api/test/<str:token>/submit/', views.SubmitTestView.as_view(), name='submit_test'),
    path('pending/', views.StudentPendingAssessmentsView.as_view(), name='pending_assessments'),
]