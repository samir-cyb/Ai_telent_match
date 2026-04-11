import uuid
import secrets
from django.db import models
from django.utils import timezone
from datetime import timedelta
from core.models import Job, Student, Application

class VettingChallenge(models.Model):
    """Coding challenge generated for a specific job"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name='vetting_challenge')
    title = models.CharField(max_length=300)
    description = models.TextField()
    starter_code = models.TextField()
    test_cases = models.JSONField(default=list)  # [{"input": "...", "expected": "...", "weight": 1}]
    language = models.CharField(max_length=50, default='python', choices=[
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
        ('java', 'Java'),
        ('cpp', 'C++')
    ])
    difficulty = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard')
    ], default='medium')
    time_limit_minutes = models.IntegerField(default=45)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    # AI Generated metadata
    skill_tags = models.JSONField(default=list)  # ["django", "orm", "api"]
    ai_prompt_used = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.title} ({self.job.title})"

class VettingSession(models.Model):
    """Individual test session for a student"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cheating_detected', 'Cheating Detected')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    challenge = models.ForeignKey(VettingChallenge, on_delete=models.CASCADE, related_name='sessions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='vetting_sessions')
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='vetting_session')
    
    # Access control
    access_token = models.CharField(max_length=64, unique=True, db_index=True)
    token_expires_at = models.DateTimeField()
    
    # Timing (Flexible Window + Fixed Duration)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    window_start = models.DateTimeField()  # When they can start
    window_end = models.DateTimeField()    # Must start before this
    max_duration_minutes = models.IntegerField(default=45)
    
    # Anti-cheat logs
    tab_switch_count = models.IntegerField(default=0)
    copy_paste_attempts = models.IntegerField(default=0)
    fullscreen_exits = models.IntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.access_token:
            self.access_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)
    
    def is_token_valid(self):
        return timezone.now() < self.token_expires_at
    
    def can_start(self):
        now = timezone.now()
        return self.window_start <= now <= self.window_end and self.status == 'pending'
    
    def has_time_remaining(self):
        if not self.started_at:
            return True
        elapsed = (timezone.now() - self.started_at).seconds / 60
        return elapsed < self.max_duration_minutes
    
    def get_time_remaining_seconds(self):
        if not self.started_at:
            return self.max_duration_minutes * 60
        elapsed = (timezone.now() - self.started_at).seconds
        remaining = (self.max_duration_minutes * 60) - elapsed
        return max(0, remaining)

class CodeSubmission(models.Model):
    """Individual code submissions during test"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(VettingSession, on_delete=models.CASCADE, related_name='submissions')
    code = models.TextField()
    language = models.CharField(max_length=50)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_final = models.BooleanField(default=False)
    
    # Execution results
    execution_output = models.TextField(blank=True)
    execution_error = models.TextField(blank=True)
    execution_time = models.FloatField(null=True, blank=True)
    memory_used = models.FloatField(null=True, blank=True)
    test_cases_passed = models.IntegerField(default=0)
    total_test_cases = models.IntegerField(default=0)

class VettingResult(models.Model):
    """Final grading result (Option B: Separate from Application)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(VettingSession, on_delete=models.CASCADE, related_name='result')
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='vetting_result')
    
    # 3-Layer Grading
    layer1_test_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # 50%
    layer2_static_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # 30%
    layer3_ai_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, null=True, blank=True)  # 20%
    final_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Details
    test_case_results = models.JSONField(default=list)
    static_analysis_report = models.JSONField(default=dict)
    ai_feedback = models.TextField(blank=True)
    code_quality_issues = models.JSONField(default=list)
    passed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def calculate_final_score(self):
        """Weighted: 50% tests, 30% static, 20% AI"""
        l1 = float(self.layer1_test_score) * 0.50
        l2 = float(self.layer2_static_score) * 0.30
        l3 = float(self.layer3_ai_score or 0) * 0.20
        self.final_score = l1 + l2 + l3
        self.passed = self.final_score >= 70
        return self.final_score