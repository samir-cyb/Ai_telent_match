from django.contrib import admin
from .models import VettingChallenge, VettingSession, VettingResult, CodeSubmission

@admin.register(VettingChallenge)
class VettingChallengeAdmin(admin.ModelAdmin):
    list_display = ['title', 'job', 'difficulty', 'language', 'is_active', 'created_at']
    list_filter = ['difficulty', 'language', 'is_active']
    search_fields = ['title', 'job__title']

@admin.register(VettingSession)
class VettingSessionAdmin(admin.ModelAdmin):
    list_display = ['student', 'challenge', 'status', 'started_at', 'completed_at']
    list_filter = ['status', 'challenge__job']
    readonly_fields = ['access_token']

@admin.register(VettingResult)
class VettingResultAdmin(admin.ModelAdmin):
    list_display = ['application', 'final_score', 'passed', 'created_at']
    list_filter = ['passed']

@admin.register(CodeSubmission)
class CodeSubmissionAdmin(admin.ModelAdmin):
    list_display = ['session', 'submitted_at', 'is_final', 'test_cases_passed']
    list_filter = ['is_final']