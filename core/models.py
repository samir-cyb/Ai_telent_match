import uuid
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Avg, Count   # <-- added for the new method

class Skill(models.Model):
    CATEGORY_CHOICES = [
        # Technology
        ('Frontend', 'Frontend'),
        ('Backend', 'Backend'),
        ('AI/ML', 'AI/ML'),
        ('DevOps', 'DevOps'),
        ('Data Science', 'Data Science'),
        ('Mobile', 'Mobile Development'),
        ('Cybersecurity', 'Cybersecurity'),
        # Non-Tech
        ('Design', 'Design & Creative'),
        ('Business', 'Business & Management'),
        ('Finance', 'Finance & Accounting'),
        ('Marketing', 'Marketing & Sales'),
        ('Engineering', 'Engineering'),
        ('Research', 'Research & Analytics'),
        ('Communication', 'Communication & Languages'),
        ('Soft Skills', 'Soft Skills'),
        ('Uncategorized', 'Uncategorized'),
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
    
    # Department category (auto-derived from department field)
    DEPARTMENT_CATEGORY_CHOICES = [
        ('tech', 'Technology & Software'),
        ('engineering', 'Engineering'),
        ('business', 'Business & Management'),
        ('design', 'Design & Creative'),
        ('science', 'Science & Research'),
        ('humanities', 'Humanities & Liberal Arts'),
        ('any', 'General / Other'),
    ]
    department_category = models.CharField(
        max_length=20, choices=DEPARTMENT_CATEGORY_CHOICES, default='any', blank=True
    )

    # External Validations
    github_username = models.CharField(max_length=100, blank=True)
    github_verified = models.BooleanField(default=False)
    github_score = models.IntegerField(default=0)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    behance_url = models.URLField(blank=True)  # For design/creative students
    resume = models.FileField(upload_to='resumes/', null=True, blank=True)

    # LinkedIn PDF verification
    linkedin_pdf = models.FileField(upload_to='linkedin_pdfs/', null=True, blank=True)
    linkedin_score = models.IntegerField(default=0)          # 0–100 computed score
    linkedin_parsed_data = models.JSONField(default=dict)    # raw parsed data from PDF

    # Non-tech enrichment fields
    certifications = models.JSONField(default=list)   # [{name, issuer, year, url}]
    eca_activities = models.JSONField(default=list)   # [{title, role, duration}]
    research_papers = models.JSONField(default=list)  # [{title, venue, year, url}]
    
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
    
    # Map specific department strings to a category group
    DEPARTMENT_GROUP_MAP = {
        # Tech
        'CSE': 'tech', 'SWE': 'tech', 'IT': 'tech', 'CS': 'tech',
        'Computer Science': 'tech', 'Computer Science & Engineering': 'tech',
        'Data Science': 'tech', 'Cybersecurity': 'tech',
        # Engineering
        'EEE': 'engineering', 'ECE': 'engineering', 'ME': 'engineering',
        'CE': 'engineering', 'ChE': 'engineering', 'BME': 'engineering',
        'Electrical & Electronic Engineering': 'engineering',
        'Mechanical Engineering': 'engineering', 'Civil Engineering': 'engineering',
        # Business
        'BBA': 'business', 'MBA': 'business', 'Finance': 'business',
        'Marketing': 'business', 'Management': 'business', 'Accounting': 'business',
        'HRM': 'business', 'Business Administration': 'business',
        # Design
        'Design': 'design', 'Fine Arts': 'design', 'Architecture': 'design',
        'UI/UX': 'design', 'Graphic Design': 'design',
        # Science
        'Physics': 'science', 'Chemistry': 'science', 'Biology': 'science',
        'Mathematics': 'science', 'Statistics': 'science',
        'Mathematics & Statistics': 'science',
        # Humanities
        'English': 'humanities', 'Journalism': 'humanities', 'Economics': 'humanities',
        'Sociology': 'humanities', 'History': 'humanities',
        'Political Science': 'humanities', 'Media': 'humanities',
        'Liberal Arts': 'humanities',
    }

    def get_department_category(self):
        """Derive the department category from the department string."""
        return self.DEPARTMENT_GROUP_MAP.get(self.department, 'any')

    def save(self, *args, **kwargs):
        """Auto-populate department_category before saving."""
        if self.department:
            self.department_category = self.get_department_category()
        super().save(*args, **kwargs)

    def calculate_profile_completeness(self):
        """Calculate how complete the profile is (0-1), department-aware."""
        # Core fields every student needs
        core_fields = [self.name, self.email, self.department, self.cgpa]
        filled = sum(1 for f in core_fields if f)
        base_score = filled / len(core_fields)

        skills_count = StudentSkill.objects.filter(student=self).count()
        projects_count = self.projects.count()

        skills_bonus = min(skills_count / 5, 0.15)
        projects_bonus = min(projects_count / 3, 0.15)

        # Department-specific bonus signals
        dept_cat = self.department_category or self.get_department_category()
        dept_bonus = 0.0
        if dept_cat == 'tech':
            if self.github_username:
                dept_bonus += 0.1
            if self.linkedin_url:
                dept_bonus += 0.05
        elif dept_cat == 'design':
            if self.behance_url or self.portfolio_url:
                dept_bonus += 0.1
            if self.linkedin_url:
                dept_bonus += 0.05
        elif dept_cat in ('business', 'humanities'):
            if self.linkedin_url:
                dept_bonus += 0.1
            if self.eca_activities:
                dept_bonus += 0.05
        elif dept_cat == 'science':
            if self.research_papers:
                dept_bonus += 0.1
            if self.linkedin_url:
                dept_bonus += 0.05
        else:
            if self.linkedin_url:
                dept_bonus += 0.05

        if self.certifications:
            dept_bonus += 0.05

        return min(base_score + skills_bonus + projects_bonus + dept_bonus, 1.0)
    
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

    def calculate_hire_readiness(self):
        """
        Returns a dict: {
            'score': int (0-100),
            'days_estimate': int,
            'label': str,
            'factors': dict
        }
        """
        # 1. Profile completeness (0-1)
        profile_score = float(self.profile_complete_score or 0)

        # 2. Skill demand fit – compare student's skills with top demanded skills
        from core.models import Skill
        top_skills = Skill.objects.annotate(
            job_count=Count('job__required_skills')
        ).order_by('-job_count').values_list('name', flat=True)[:20]
        top_skills_set = set(top_skills)
        student_skill_names = {ss.skill.name for ss in self.student_skills.select_related('skill')}
        matched = len(student_skill_names & top_skills_set)
        total_skills = len(student_skill_names)
        demand_score = (matched / max(total_skills, 1)) if total_skills > 0 else 0.0

        # 3. Application activity – applications per week, average match score
        from django.utils import timezone
        from datetime import timedelta
        week_ago = timezone.now() - timedelta(days=7)
        recent_apps = self.applications.filter(applied_at__gte=week_ago).count()
        avg_match = float(self.applications.aggregate(avg=Avg('match_score'))['avg'] or 0)
        # Encourage activity: more recent apps = better (capped at 10 per week)
        activity_score = min(recent_apps / 5, 1.0) if recent_apps > 0 else 0.0
        # Match score contribution (normalized 0-1)
        match_score = avg_match / 100.0

        # 4. External validation – trust score, GitHub, LinkedIn
        trust = float(self.trust_score or 0) / 100.0
        github_bonus = 0.1 if self.github_verified else 0.0
        linkedin_bonus = 0.05 if self.linkedin_url else 0.0

        # Weighted combination (adjust weights as needed)
        weights = {
            'profile': 0.25,
            'demand': 0.20,
            'activity': 0.15,
            'match': 0.20,
            'trust': 0.15,
            'github': 0.05,
            'linkedin': 0.05,
        }
        raw_score = (
            profile_score * weights['profile'] +
            demand_score * weights['demand'] +
            activity_score * weights['activity'] +
            match_score * weights['match'] +
            trust * weights['trust'] +
            github_bonus * weights['github'] +
            linkedin_bonus * weights['linkedin']
        )
        # Normalise to 0-100
        raw_score = min(1.0, raw_score) * 100
        score = int(round(raw_score))

        # Map score to days estimate
        if score >= 90:
            days = 7 + (14-7) * (1 - (score-90)/10)  # 7-14
            label = "Excellent"
        elif score >= 70:
            days = 15 + (30-15) * (1 - (score-70)/20)  # 15-30
            label = "Good"
        elif score >= 50:
            days = 31 + (60-31) * (1 - (score-50)/20)  # 31-60
            label = "Fair"
        elif score >= 30:
            days = 61 + (90-61) * (1 - (score-30)/20)  # 61-90
            label = "Needs Improvement"
        else:
            days = 91 + (180-91) * (1 - (score)/30)  # 91-180
            label = "Significant Gaps"

        days_estimate = int(round(days))

        return {
            'score': score,
            'days_estimate': days_estimate,
            'label': label,
            'factors': {
                'profile_completeness': round(profile_score * 100),
                'skill_demand_fit': round(demand_score * 100),
                'application_activity': round(activity_score * 100),
                'average_match_score': round(match_score * 100),
                'trust_score': round(trust * 100),
            }
        }

class LeaderboardEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='leaderboard')
    total_points = models.IntegerField(default=0)
    university = models.CharField(max_length=200, blank=True)  # derived from student.university_id or profile
    last_updated = models.DateTimeField(auto_now=True)
    awarded_actions = models.JSONField(default=list)  # list of action strings already awarded

    class Meta:
        ordering = ['-total_points']

    def __str__(self):
        return f"{self.student.name} - {self.total_points} pts"
    

class StudentSkill(models.Model):
    PROFICIENCY_LEVELS = [
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Expert', 'Expert'),
    ]
    SOURCE_CHOICES = [
        ('cv', 'CV Upload'),
        ('linkedin', 'LinkedIn PDF'),
        ('manual', 'Manually Added'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='student_skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    proficiency_level = models.CharField(max_length=20, choices=PROFICIENCY_LEVELS)
    verified_via = models.CharField(max_length=50, blank=True, null=True)
    # Cross-validation: True when this skill appears in BOTH CV and LinkedIn PDF
    cross_validated = models.BooleanField(default=False)
    # Where was this skill first added from?
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'skill']

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')  # FIX: Allow blank, default to empty string
    github_url = models.URLField(blank=True, null=True)
    live_url = models.URLField(blank=True, null=True)
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
    description = models.TextField(blank=True, default='')  # FIX: Allow blank, default to empty string

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
    
    # Target department category for this job
    DEPARTMENT_CATEGORY_CHOICES = [
        ('tech', 'Technology & Software'),
        ('engineering', 'Engineering'),
        ('business', 'Business & Management'),
        ('design', 'Design & Creative'),
        ('science', 'Science & Research'),
        ('humanities', 'Humanities & Liberal Arts'),
        ('any', 'Open to All Departments'),
    ]
    department_category = models.CharField(
        max_length=20, choices=DEPARTMENT_CATEGORY_CHOICES, default='any', blank=True
    )

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
    """Log of AI weight adjustments — every hire, reject, and manual edit is recorded."""
    TRIGGER_CHOICES = [
        ('hire',   'Candidate Hired'),
        ('reject', 'Shortlisted Candidate Rejected'),
        ('manual', 'Company Manually Edited Weights'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ai_feedback_logs')
    application = models.ForeignKey(
        Application, on_delete=models.SET_NULL, related_name='ai_feedback',
        null=True, blank=True  # null for manual edits
    )
    trigger          = models.CharField(max_length=10, choices=TRIGGER_CHOICES, default='hire')
    reward           = models.FloatField(default=1.0)          # +1 hire, -1 reject, 0 manual
    candidate_features = models.JSONField(default=dict)         # normalised feature scores
    previous_weights = models.JSONField(default=dict)
    adjusted_weights = models.JSONField(default=dict)
    weight_delta     = models.JSONField(default=dict)           # adjusted - previous per key
    adjustment_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.trigger.upper()}] {self.company.name} — {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    
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
    meeting_type = models.CharField(max_length=20, default='in_person')  # in_person, online, phone
    location = models.CharField(max_length=500, blank=True)        # Office address for in-person
    contact_person = models.CharField(max_length=200, blank=True)  # Interviewer name/contact
    
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

class AIInterview(models.Model):
    """AI-powered interview: company generates questions, candidate answers, Gemini scores."""
    STATUS_CHOICES = [
        ('pending',     'Pending — link sent, not started'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application     = models.ForeignKey('Application', on_delete=models.CASCADE, related_name='ai_interviews')
    agent_run       = models.ForeignKey('RecruitmentAgentRun', on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='interviews')
    questions       = models.JSONField(default=list)   # [{question, type, target, good_answer_includes}]
    answers         = models.JSONField(default=list)   # [{q_index, answer, score, feedback, answered_at}]
    interview_score = models.FloatField(null=True, blank=True)   # 0–100 avg of answer scores
    combined_score  = models.FloatField(null=True, blank=True)   # 40% agent + 60% interview
    status          = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    token           = models.CharField(max_length=64, unique=True)   # URL access token
    email_sent      = models.BooleanField(default=False)
    expires_at      = models.DateTimeField(null=True, blank=True)    # Company-set deadline
    gemini_analysis = models.JSONField(null=True, blank=True)        # Full Gemini analysis result
    cheating_log    = models.JSONField(null=True, blank=True)        # Anti-cheat violation log
    created_at      = models.DateTimeField(auto_now_add=True)
    completed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Interview: {self.application.student.name} — {self.status}"

    def get_next_question_index(self):
        """Return index of next unanswered question."""
        return len(self.answers)

    def is_complete(self):
        return len(self.answers) >= len(self.questions) and len(self.questions) > 0


class RecruitmentAgentRun(models.Model):
    """One run of the Recruitment Agent for a single application."""
    TRIGGERED_BY_CHOICES = [
        ('auto',   'Auto — triggered on apply'),
        ('manual', 'Manual — company re-run'),
    ]
    DECISION_CHOICES = [
        ('shortlist', 'Shortlist'),
        ('reject',    'Reject'),
        ('review',    'Manual Review'),
    ]
    STATUS_CHOICES = [
        ('running',   'Running'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application     = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='agent_runs')
    triggered_by    = models.CharField(max_length=10, choices=TRIGGERED_BY_CHOICES, default='auto')
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES, default='running')
    score           = models.FloatField(default=0.0)
    decision        = models.CharField(max_length=10, choices=DECISION_CHOICES, default='review')
    confidence      = models.CharField(max_length=10, default='LOW')  # HIGH / MEDIUM / LOW
    reasoning_steps = models.JSONField(default=list)    # [{step, action, thought, result, data, timestamp}]
    fit_report      = models.JSONField(default=dict)    # {strengths, gaps, recommendation, feature_breakdown}
    weights_used    = models.JSONField(default=dict)    # snapshot of company weights at run time
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"[{self.decision.upper()}] {self.application.student.name} "
            f"@ {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        )


class InterviewNotification(models.Model):
    """Track interview notifications"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interview = models.ForeignKey(ScheduledInterview, on_delete=models.CASCADE, related_name='notifications')
    recipient_type = models.CharField(max_length=20)  # student, company
    notification_type = models.CharField(max_length=50)  # scheduled, reminder, cancelled, updated
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
