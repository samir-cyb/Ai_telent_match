from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from core.models import Student   # for vetting helper

def send_email_notification(user, subject, template_name, context, to_email=None):
    if not to_email and hasattr(user, 'email'):
        to_email = user.email
    if not to_email:
        return
    html_message = render_to_string(f'email/{template_name}.html', context)
    plain_message = strip_tags(html_message)
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        html_message=html_message,
        fail_silently=False,
    )

# --- Existing helpers (shortlist, interview) ---
def send_shortlist_email(application):
    student = application.student
    job = application.job
    context = {
        'student_name': student.name,
        'job_title': job.title,
        'company_name': job.company.name,
        'match_score': application.match_score,
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"🎉 You've been shortlisted for {job.title}!",
        template_name='shortlist',
        context=context,
    )

def send_interview_email(interview):
    app = interview.application
    student = app.student
    job = app.job
    context = {
        'student_name': student.name,
        'job_title': job.title,
        'company_name': job.company.name,
        'interview_date': interview.date,
        'interview_time': interview.start_time,
        'meeting_link': interview.meeting_link or 'Will be shared soon',
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"📅 Interview Scheduled for {job.title}",
        template_name='interview_scheduled',
        context=context,
    )

# --- NEW helpers ---
def send_application_confirmation_email(application):
    student = application.student
    job = application.job
    context = {
        'student_name': student.name,
        'job_title': job.title,
        'company_name': job.company.name,
        'match_score': application.match_score,
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"✅ Application submitted for {job.title}",
        template_name='application_confirmation',
        context=context,
    )

def send_auto_apply_email(application):
    student = application.student
    job = application.job
    context = {
        'student_name': student.name,
        'job_title': job.title,
        'company_name': job.company.name,
        'match_score': application.match_score,
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"🤖 Auto-applied to {job.title}",
        template_name='auto_apply',
        context=context,
    )

def send_hired_email(application):
    student = application.student
    job = application.job
    context = {
        'student_name': student.name,
        'job_title': job.title,
        'company_name': job.company.name,
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"🎉 You've been hired for {job.title}!",
        template_name='hired',
        context=context,
    )

def send_rejected_email(application):
    student = application.student
    job = application.job
    context = {
        'student_name': student.name,
        'job_title': job.title,
        'company_name': job.company.name,
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"❌ Application update for {job.title}",
        template_name='rejected',
        context=context,
    )

def send_vetting_invitation_email(notification):
    """Send assessment invitation email to student."""
    student = Student.objects.get(id=notification.user_id)
    context = {
        'student_name': student.name,
        'challenge_title': notification.title,
        'test_url': notification.data.get('test_url'),
        'company_name': notification.data.get('company_name', 'the company'),
        'job_title': notification.data.get('job_title', 'the position'),
        'dashboard_url': '/student/dashboard/',
    }
    send_email_notification(
        student,
        subject=f"🧠 Technical Assessment Invitation",
        template_name='vetting_invitation',
        context=context,
    )