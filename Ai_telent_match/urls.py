from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from vetting.views import SubmissionDetailView
from core.views import (
    InterviewSlotAvailabilityView, landing_page, about_us, services,
    student_login, student_register, student_dashboard, student_profile, student_job_detail, student_jobs,  # ADD student_jobs HERE
    company_login, company_register, company_dashboard, company_post_job, company_applicants,
    admin_dashboard, admin_analytics, admin_fraud_review, StudentLogoutView, CompanyLogoutView ,admin_login_page, ApplicationsListView
)

urlpatterns = [
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
    
    # Company
    path('company/dashboard/', company_dashboard, name='company_dashboard'),
    path('company/post-job/', company_post_job, name='company_post_job'),
    path('company/applicants/', company_applicants, name='company_applicants'),
    path('api/auth/company/logout/', CompanyLogoutView.as_view(), name='company_logout'),
    
    # Admin
    path('admin/dashboard/', admin_dashboard, name='admin_dashboard'),
    path('admin/analytics/', admin_analytics, name='admin_analytics'),
    path('admin/fraud-review/', admin_fraud_review, name='admin_fraud_review'),
    path('admin/login/', admin_login_page, name='admin_login_page'),
    path('admin/', admin.site.urls),
    path('applications/', ApplicationsListView.as_view()),
    path('job/<uuid:job_id>/slot-availability/', InterviewSlotAvailabilityView.as_view()),
    # API
    path('api/', include('core.urls')),
    
    #vetting
    path('vetting/', include('vetting.urls')),  # ADD THIS LINE
    path('vetting/api/', include('vetting.urls')),
    path('vetting/submission/<uuid:submission_id>/', SubmissionDetailView.as_view(), name='submission_detail'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])