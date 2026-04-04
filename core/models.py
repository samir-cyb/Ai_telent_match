import uuid
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from datetime import datetime, timedelta
from django.utils import timezone
class Skill(models.Model):
    CATEGORY_CHOICES = [
        ('Frontend', 'Frontend'),
        ('Backend', 'Backend'),
        ('AI/ML', 'AI/ML'),
        ('Design', 'Design'),
        ('Soft Skills', 'Soft Skills'),
        ('DevOps', 'DevOps'),
        ('Data Science', 'Data Science'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    verification_method = models.CharField(max_length=50, default='self_reported')
    
    def __str__(self):
        return f"{self.name} ({self.category})"

class Student(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # Hashed password
    university_id = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    department = models.CharField(max_length=100)
    cgpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    graduation_date = models.DateField(null=True, blank=True)
    
    # Preferences stored as JSON
    preferences = models.JSONField(default=dict)  # job_types, salary_expectation, company_size, relocate
    
    # External Validations
    github_username = models.CharField(max_length=100, blank=True)
    github_verified = models.BooleanField(default=False)
    github_score = models.IntegerField(default=0)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    
    # Trust Scores
    profile_complete_score = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    activity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    trust_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    
    # Behavioral
    last_login = models.DateTimeField(null=True, blank=True)
    login_frequency = models.IntegerField(default=0)
    total_session_duration = models.IntegerField(default=0)  # minutes
    
    # A/B Testing
    ab_test_group = models.CharField(max_length=10, default='control')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
    
    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
    
    def calculate_profile_completeness(self):
        """Calculate how complete the profile is (0-1)"""
        fields = [
            self.name, self.email, self.department, self.cgpa,
            self.github_username, self.linkedin_url
        ]
        filled = sum(1 for f in fields if f)
        skills_count = StudentSkill.objects.filter(student=self).count()
        projects_count = self.projects.count()
        
        base_score = filled / len(fields)
        skills_bonus = min(skills_count / 5, 0.2)  # Max 0.2 bonus for 5+ skills
        projects_bonus = min(projects_count / 3, 0.2)  # Max 0.2 bonus for 3+ projects
        
        return min(base_score + skills_bonus + projects_bonus, 1.0)
    
    def calculate_trust_score(self):
        """Calculate trust score based on multiple factors"""
        profile_weight = 0.3
        activity_weight = 0.3
        project_weight = 0.4
        
        # Profile completeness (0-1) - Convert Decimal to float
        self.profile_complete_score = self.calculate_profile_completeness()
        profile_score = float(self.profile_complete_score)  # FIX: Convert to float
        
        # Activity normalized (assume 100 is max) - Convert Decimal to float
        activity_score = min(float(self.activity_score) / 100, 1.0)  # FIX: Convert to float
        
        # Projects count (assume 5+ is max score)
        project_count = self.projects.count()
        project_score = min(project_count / 5.0, 1.0)
        
        trust = (profile_score * profile_weight + 
                activity_score * activity_weight + 
                project_score * project_weight) * 100
        
        self.trust_score = trust
        self.save()
        return trust

class StudentSkill(models.Model):
    PROFICIENCY_LEVELS = [
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Expert', 'Expert'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='student_skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    proficiency_level = models.CharField(max_length=20, choices=PROFICIENCY_LEVELS)
    verified_via = models.CharField(max_length=50, blank=True, null=True)  # <-- ADD null=True HERE
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'skill']

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=300)
    description = models.TextField()
    github_url = models.URLField(blank=True)
    live_url = models.URLField(blank=True)
    tech_stack = models.ManyToManyField(Skill)
    duration_weeks = models.IntegerField(null=True, blank=True)
    complexity_score = models.IntegerField(default=1)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['student', 'title']  # ADD THIS LINE
    
    def __str__(self):
        return f"{self.title} ({self.student.name})"

class WorkExperience(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='experiences')
    company_name = models.CharField(max_length=200)
    role = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=50, default='pending')
    verification_method = models.CharField(max_length=50, blank=True)
    description = models.TextField()

class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # Hashed password
    name = models.CharField(max_length=200)
    industry = models.CharField(max_length=100)
    size = models.CharField(max_length=50)  # Startup, Mid, Enterprise
    website = models.URLField(blank=True)
    verified = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    
    # Dynamic Weights (JSON)
    custom_weights = models.JSONField(default=dict)
    successful_hire_patterns = models.JSONField(default=list)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
    
    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
    
    def get_weights(self):
        """Return weights, using defaults if not set"""
        default = {
            'skills': 0.4,
            'cgpa': 0.2,
            'projects': 0.2,
            'activity': 0.1,
            'trust': 0.1
        }
        return {**default, **self.custom_weights}

class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='jobs')
    title = models.CharField(max_length=300)
    description = models.TextField()
    required_skills = models.ManyToManyField(Skill)
    min_cgpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    job_type = models.CharField(max_length=50)  # Remote, Hybrid, On-site
    salary_range = models.JSONField(default=dict)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=50, default='active')
    total_applicants = models.IntegerField(default=0)
    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Job-specific weights override
    custom_weights = models.JSONField(default=dict, blank=True)

class Application(models.Model):
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('shortlisted', 'Shortlisted'),
        ('interview', 'Interview'),
        ('rejected', 'Rejected'),
        ('hired', 'Hired'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='applications')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    match_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='applied')
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_auto_applied = models.BooleanField(default=False)

class MatchExplanation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='explanation')
    score_breakdown = models.JSONField()  # Detailed component scores
    skill_gaps = models.ManyToManyField(Skill, blank=True)
    recommendations = models.JSONField(default=list)  # Array of text advice
    radar_chart_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class StudentBehaviorLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='behavior_logs')
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)  # viewed, saved, ignored, applied, dismissed
    duration_seconds = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

class SkillAssessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assessments')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    score = models.IntegerField()  # 0-100
    taken_at = models.DateTimeField(auto_now_add=True)
    assessment_type = models.CharField(max_length=50)  # quiz, coding_challenge, project_review

class FraudFlag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fraud_flags')
    flag_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=20)  # low, medium, high
    details = models.JSONField(default=dict)
    reviewed_by = models.UUIDField(null=True, blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class InterviewSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interviews')
    proposed_times = models.JSONField(default=list)  # Array of timestamps
    finalized_time = models.DateTimeField(null=True, blank=True)
    meeting_link = models.URLField(blank=True)
    status = models.CharField(max_length=50, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)  # Add this line
    updated_at = models.DateTimeField(auto_now=True) 

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField()  # Generic FK to student or company
    user_type = models.CharField(max_length=20)  # 'student' or 'company'
    type = models.CharField(max_length=100)  # match, interview, shortlist, fraud_alert
    title = models.CharField(max_length=300)
    message = models.TextField()
    read = models.BooleanField(default=False)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class AIFeedbackLog(models.Model):
    """Log of AI weight adjustments based on hiring feedback"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ai_feedback_logs')
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='ai_feedback')
    previous_weights = models.JSONField(default=dict)
    adjusted_weights = models.JSONField(default=dict)
    adjustment_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"AI Feedback for {self.company.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    
class Admin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # Hashed
    is_super_admin = models.BooleanField(default=False)  # Only you
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
    
    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
    
    def __str__(self):
        return f"{self.email} ({'Super' if self.is_super_admin else 'Admin'})"
class InterviewSlot(models.Model):
    """Pre-defined interview slots set by company"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='interview_slots')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='interview_slots')
    
    # Slot configuration
    date = models.DateField()
    start_time = models.TimeField()  # e.g., 09:00
    end_time = models.TimeField()    # e.g., 17:00
    slot_duration_minutes = models.IntegerField(default=30)  # 30, 45, 60 min slots
    
    # Break configuration (optional)
    break_start = models.TimeField(null=True, blank=True)  # e.g., 13:00 lunch
    break_end = models.TimeField(null=True, blank=True)    # e.g., 14:00
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # THIS METHOD MUST BE INDENTED INSIDE THE CLASS (4 spaces)
    def generate_time_slots(self):
        """Generate individual time slots based on configuration"""
        from datetime import datetime, timedelta  # Local import
        
        slots = []
        
        # Ensure self.date is a date object
        slot_date = self.date
        if isinstance(slot_date, str):
            slot_date = datetime.strptime(slot_date, '%Y-%m-%d').date()
        
        # Convert time fields if they're strings
        start = self.start_time
        if isinstance(start, str):
            start = datetime.strptime(start, '%H:%M').time()
        
        end = self.end_time
        if isinstance(end, str):
            end = datetime.strptime(end, '%H:%M').time()
        
        current_time = datetime.combine(slot_date, start)
        end_datetime = datetime.combine(slot_date, end)
        
        # Handle break times similarly...
        break_start = None
        if self.break_start:
            break_start_time = self.break_start
            if isinstance(break_start_time, str):
                break_start_time = datetime.strptime(break_start_time, '%H:%M').time()
            break_start = datetime.combine(slot_date, break_start_time)
        
        break_end = None
        if self.break_end:
            break_end_time = self.break_end
            if isinstance(break_end_time, str):
                break_end_time = datetime.strptime(break_end_time, '%H:%M').time()
            break_end = datetime.combine(slot_date, break_end_time)
        
        duration = timedelta(minutes=self.slot_duration_minutes)
        
        while current_time + duration <= end_datetime:
            slot_end = current_time + duration
            
            # Skip if during break time
            if break_start and break_end:
                if not (current_time >= break_end or slot_end <= break_start):
                    current_time = break_end
                    continue
            
            # Check if slot is already booked
            is_booked = ScheduledInterview.objects.filter(
                slot=self,
                start_time=current_time.time()
            ).exists()
            
            slots.append({
                'start': current_time.strftime('%H:%M'),
                'end': slot_end.strftime('%H:%M'),
                'available': not is_booked
            })
            
            current_time = slot_end
        
        # RETURN MUST BE OUTSIDE THE WHILE LOOP (4 spaces indentation)
        return slots
    
    def __str__(self):
        return f"{self.job.title} - {self.date} ({self.start_time}-{self.end_time})"

class ScheduledInterview(models.Model):
    """Actual scheduled interviews"""
    STATUS_CHOICES = [
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='scheduled_interview')
    slot = models.ForeignKey(InterviewSlot, on_delete=models.CASCADE, related_name='scheduled_interviews', null=True, blank=True)
    
    # Interview details
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    meeting_link = models.URLField(blank=True)
    meeting_type = models.CharField(max_length=20, default='online')  # online, in_person, phone
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    company_notes = models.TextField(blank=True)
    student_notes = models.TextField(blank=True)
    
    # Notifications
    company_notified = models.BooleanField(default=False)
    student_notified = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Interview: {self.application.student.name} for {self.application.job.title}"


class InterviewNotification(models.Model):
    """Track interview notifications"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interview = models.ForeignKey(ScheduledInterview, on_delete=models.CASCADE, related_name='notifications')
    recipient_type = models.CharField(max_length=20)  # student, company
    notification_type = models.CharField(max_length=50)  # scheduled, reminder, cancelled, updated
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)