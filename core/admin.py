from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.http import HttpResponseRedirect
from django.contrib import messages

from core.models import (
    Student, Company, Job, Application, Skill, StudentSkill,
    Project, WorkExperience, FraudFlag, MatchExplanation,
    StudentBehaviorLog, AIFeedbackLog, InterviewSchedule,
    Notification, SkillAssessment
)
from core.utils.fraud_detector import FraudDetectionEngine


class StudentSkillInline(admin.TabularInline):
    model = StudentSkill
    extra = 1
    fields = ['skill', 'proficiency_level', 'verified_via', 'verified_at']


class ProjectInline(admin.StackedInline):
    model = Project
    extra = 0
    fields = ['title', 'description', 'github_url', 'complexity_score', 'verified']


class WorkExperienceInline(admin.StackedInline):
    model = WorkExperience
    extra = 0
    fields = ['company_name', 'role', 'start_date', 'end_date', 'is_current', 'verification_status']


class ApplicationInline(admin.TabularInline):
    model = Application
    extra = 0
    fields = ['job', 'match_score', 'status', 'is_auto_applied', 'applied_at']
    readonly_fields = ['applied_at']
    show_change_link = True


class FraudFlagInline(admin.TabularInline):
    model = FraudFlag
    extra = 0
    fields = ['flag_type', 'severity', 'resolved', 'created_at']
    readonly_fields = ['created_at']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'email', 'department', 'cgpa', 'trust_score_display',
        'github_verified', 'project_count', 'application_count', 'created_at'
    ]
    list_filter = ['department', 'github_verified', 'ab_test_group', 'created_at']
    search_fields = ['name', 'email', 'university_id']
    readonly_fields = [
        'trust_score', 'github_score', 'activity_score',
        'profile_complete_score', 'login_frequency', 'total_session_duration'
    ]
    inlines = [StudentSkillInline, ProjectInline, WorkExperienceInline, ApplicationInline, FraudFlagInline]
    actions = ['run_fraud_detection', 'assign_ab_test_variant', 'recalculate_trust_score']
    
    def trust_score_display(self, obj):
        color = 'green' if obj.trust_score >= 70 else 'orange' if obj.trust_score >= 50 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}</span>',
            color, obj.trust_score
        )
    trust_score_display.short_description = 'Trust Score'
    
    def project_count(self, obj):
        return obj.projects.count()
    project_count.short_description = 'Projects'
    
    def application_count(self, obj):
        return obj.applications.count()
    application_count.short_description = 'Applications'
    
    def run_fraud_detection(self, request, queryset):
        engine = FraudDetectionEngine()
        total_flags = 0
        
        for student in queryset:
            flags = engine.analyze_student(student)
            total_flags += len(flags)
        
        self.message_user(
            request,
            f'Fraud detection completed. {total_flags} new flags raised.',
            messages.SUCCESS if total_flags > 0 else messages.INFO
        )
    run_fraud_detection.short_description = "Run fraud detection on selected students"
    
    def assign_ab_test_variant(self, request, queryset):
        from core.utils.ai_engine import ABTestFramework
        variants = {'control': 0, 'variant_a': 0, 'variant_b': 0}
        
        for student in queryset:
            if not student.ab_test_group or student.ab_test_group == 'control':
                variant = ABTestFramework.assign_variant(student)
                variants[variant] += 1
        
        self.message_user(
            request,
            f'A/B test variants assigned: Control={variants["control"]}, Variant A={variants["variant_a"]}, Variant B={variants["variant_b"]}',
            messages.SUCCESS
        )
    assign_ab_test_variant.short_description = "Assign A/B test variant to selected students"
    
    def recalculate_trust_score(self, request, queryset):
        for student in queryset:
            student.calculate_trust_score()
        
        self.message_user(
            request,
            f'Trust scores recalculated for {queryset.count()} students.',
            messages.SUCCESS
        )
    recalculate_trust_score.short_description = "Recalculate trust scores"


@admin.register(FraudFlag)
class FraudFlagAdmin(admin.ModelAdmin):
    list_display = ['student', 'flag_type', 'severity_colored', 'resolved', 'created_at', 'actions_column']
    list_filter = ['severity', 'resolved', 'flag_type', 'created_at']
    search_fields = ['student__name', 'student__email', 'flag_type']
    actions = ['resolve_flags', 'bulk_resolve']
    readonly_fields = ['created_at']
    
    def severity_colored(self, obj):
        colors = {'high': 'red', 'medium': 'orange', 'low': 'blue'}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.severity, 'black'),
            obj.severity.upper()
        )
    severity_colored.short_description = 'Severity'
    
    def actions_column(self, obj):
        if not obj.resolved:
            return format_html(
                '<a class="button" href="{}">Resolve</a>',
                f'/admin/core/fraudflag/{obj.id}/resolve/'
            )
        return 'Resolved'
    actions_column.short_description = 'Actions'
    
    def resolve_flags(self, request, queryset):
        queryset.update(resolved=True)
        self.message_user(request, f'{queryset.count()} flags marked as resolved.', messages.SUCCESS)
    resolve_flags.short_description = "Mark selected flags as resolved"
    
    def bulk_resolve(self, request, queryset):
        # Resolve all flags for selected students
        students = queryset.values_list('student', flat=True).distinct()
        FraudFlag.objects.filter(student__in=students, resolved=False).update(resolved=True)
        self.message_user(request, f'All flags resolved for {students.count()} students.', messages.SUCCESS)
    bulk_resolve.short_description = "Resolve all flags for selected students' profiles"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/resolve/',
                self.admin_site.admin_view(self.resolve_single),
                name='fraudflag-resolve'
            ),
        ]
        return custom_urls + urls
    
    def resolve_single(self, request, object_id):
        flag = FraudFlag.objects.get(id=object_id)
        flag.resolved = True
        flag.save()
        messages.success(request, f'Flag for {flag.student.name} has been resolved.')
        return HttpResponseRedirect('/admin/core/fraudflag/')


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'industry', 'size', 'verified', 'job_count', 'created_at']
    list_filter = ['industry', 'size', 'verified', 'created_at']
    search_fields = ['name', 'email']
    
    def job_count(self, obj):
        return obj.jobs.count()
    job_count.short_description = 'Posted Jobs'


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['title', 'company', 'status', 'total_applicants', 'shortlisted_count', 'created_at']
    list_filter = ['status', 'company', 'created_at']
    search_fields = ['title', 'company__name', 'description']
    filter_horizontal = ['required_skills']
    
    def shortlisted_count(self, obj):
        return obj.applications.filter(status='shortlisted').count()
    shortlisted_count.short_description = 'Shortlisted'


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'student', 'job', 'match_score_display', 'status',
        'is_auto_applied', 'applied_at', 'updated_at'
    ]
    list_filter = ['status', 'is_auto_applied', 'applied_at']
    search_fields = ['student__name', 'job__title']
    ordering = ['-match_score']
    readonly_fields = ['applied_at', 'updated_at']
    
    def match_score_display(self, obj):
        if obj.match_score is None:
            return '-'
        color = 'green' if obj.match_score >= 80 else 'orange' if obj.match_score >= 60 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color, obj.match_score
        )
    match_score_display.short_description = 'Match Score'


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'usage_count']
    list_filter = ['category']
    search_fields = ['name']
    
    def usage_count(self, obj):
        return obj.studentskill_set.count()
    usage_count.short_description = 'Students with this skill'


@admin.register(AIFeedbackLog)
class AIFeedbackLogAdmin(admin.ModelAdmin):
    list_display = ['company', 'application', 'created_at', 'adjustment_preview']
    readonly_fields = ['previous_weights', 'adjusted_weights', 'created_at']
    list_filter = ['created_at', 'company']
    
    def adjustment_preview(self, obj):
        changes = []
        for key in obj.adjusted_weights:
            old = obj.previous_weights.get(key, 0)
            new = obj.adjusted_weights.get(key, 0)
            if abs(new - old) > 0.001:
                direction = '↑' if new > old else '↓'
                changes.append(f'{key}: {direction}')
        return ', '.join(changes) if changes else 'No change'
    adjustment_preview.short_description = 'Changes'


@admin.register(StudentBehaviorLog)
class StudentBehaviorLogAdmin(admin.ModelAdmin):
    list_display = ['student', 'job', 'action', 'duration_seconds', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['student__name', 'job__title']


@admin.register(MatchExplanation)
class MatchExplanationAdmin(admin.ModelAdmin):
    list_display = ['application', 'created_at']
    readonly_fields = ['score_breakdown', 'radar_chart_data', 'recommendations']


@admin.register(InterviewSchedule)
class InterviewScheduleAdmin(admin.ModelAdmin):
    list_display = ['application', 'status', 'finalized_time', 'created_at']
    list_filter = ['status', 'created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user_type', 'type', 'title', 'read', 'created_at']
    list_filter = ['user_type', 'type', 'read', 'created_at']


@admin.register(SkillAssessment)
class SkillAssessmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'skill', 'score', 'assessment_type', 'taken_at']
    list_filter = ['assessment_type', 'taken_at']