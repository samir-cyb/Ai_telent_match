"""
Management command: create_test_data
====================================
Creates 5 diverse student profiles, 3 companies, and 8 jobs for poster testing.

Usage:
    python manage.py create_test_data
    python manage.py create_test_data --flush   # delete existing test data first
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from core.models import (
    Student, Company, Job, Skill, StudentSkill,
    WorkExperience, Project, Application
)


SKILLS_DATA = [
    'Python', 'Django', 'React', 'JavaScript', 'Machine Learning',
    'TensorFlow', 'SQL', 'PostgreSQL', 'Docker', 'AWS',
    'Data Science', 'Pandas', 'NumPy', 'Tableau', 'Power BI',
    'HTML', 'CSS', 'Node.js', 'Flutter', 'Kotlin',
    'MATLAB', 'Arduino', 'Circuit Design', 'AutoCAD', 'C++',
    'Excel', 'Marketing', 'Sales', 'Business Analysis', 'Finance',
    'Git', 'REST API', 'MongoDB', 'Redis', 'Kubernetes',
    'Communication', 'Leadership', 'Project Management',
]

STUDENTS_DATA = [
    {
        'name': 'Rahim Ahmed',
        'email': 'test_rahim@demo.com',
        'department': 'CSE',
        'department_category': 'tech',
        'cgpa': 3.82,
        'university_id': 'CSE-2021-001',
        'github_username': 'rahim-ahmed-dev',
        'github_score': 78,
        'linkedin_score': 65,
        'trust_score': 84.5,
        'profile_complete_score': 0.92,
        'activity_score': 88,
        'skills': ['Python', 'Django', 'React', 'JavaScript', 'Machine Learning', 'SQL', 'Docker', 'Git', 'REST API'],
        'experience': [
            {'company': 'BrainStation23', 'role': 'Django Backend Intern', 'start': date(2023,6,1), 'end': date(2023,12,31)},
        ],
        'projects': [
            {'title': 'E-Commerce Platform', 'desc': 'Django + React full-stack shop', 'tech': ['Django','React','PostgreSQL']},
            {'title': 'ML Price Predictor', 'desc': 'House price prediction with scikit-learn', 'tech': ['Python','ML','Pandas']},
            {'title': 'REST API Gateway', 'desc': 'Microservices API with Docker', 'tech': ['Python','Docker','Redis']},
        ],
        'tag': 'AI/ML + Full Stack (Strong Profile)',
    },
    {
        'name': 'Tasnim Haque',
        'email': 'test_tasnim@demo.com',
        'department': 'BBA',
        'department_category': 'business',
        'cgpa': 3.55,
        'university_id': 'BBA-2021-002',
        'github_username': '',
        'github_score': 0,
        'linkedin_score': 72,
        'trust_score': 71.0,
        'profile_complete_score': 0.78,
        'activity_score': 65,
        'skills': ['Excel', 'Marketing', 'Sales', 'Business Analysis', 'Finance', 'Power BI', 'Communication', 'Leadership'],
        'experience': [
            {'company': 'Grameenphone', 'role': 'Marketing Intern', 'start': date(2023,3,1), 'end': date(2023,8,31)},
        ],
        'projects': [
            {'title': 'Market Entry Strategy', 'desc': 'SME market analysis for FMCG brand', 'tech': ['Excel','PowerPoint']},
            {'title': 'Sales Dashboard', 'desc': 'Power BI dashboard for retail sales', 'tech': ['Power BI','Excel']},
        ],
        'tag': 'Business / BBA (Good Profile)',
    },
    {
        'name': 'Mehedi Hassan',
        'email': 'test_mehedi@demo.com',
        'department': 'EEE',
        'department_category': 'engineering',
        'cgpa': 3.61,
        'university_id': 'EEE-2021-003',
        'github_username': 'mehedi-eee',
        'github_score': 42,
        'linkedin_score': 40,
        'trust_score': 68.0,
        'profile_complete_score': 0.72,
        'activity_score': 55,
        'skills': ['MATLAB', 'Arduino', 'Circuit Design', 'C++', 'AutoCAD', 'Python', 'Embedded Systems'],
        'experience': [],
        'projects': [
            {'title': 'Smart Home Controller', 'desc': 'Arduino-based home automation', 'tech': ['Arduino','C++','IoT']},
            {'title': 'Power System Simulation', 'desc': 'MATLAB power grid simulation', 'tech': ['MATLAB']},
        ],
        'tag': 'Engineering (Average Profile)',
    },
    {
        'name': 'Nadia Islam',
        'email': 'test_nadia@demo.com',
        'department': 'CSE',
        'department_category': 'tech',
        'cgpa': 2.95,
        'university_id': 'CSE-2022-004',
        'github_username': 'nadia-codes',
        'github_score': 15,
        'linkedin_score': 20,
        'trust_score': 42.0,
        'profile_complete_score': 0.45,
        'activity_score': 30,
        'skills': ['HTML', 'CSS', 'JavaScript', 'Python', 'SQL'],
        'experience': [],
        'projects': [
            {'title': 'Portfolio Website', 'desc': 'Personal HTML/CSS portfolio', 'tech': ['HTML','CSS']},
        ],
        'tag': 'Junior Web Dev (Weak Profile)',
    },
    {
        'name': 'Karim Chowdhury',
        'email': 'test_karim@demo.com',
        'department': 'Data Science',
        'department_category': 'tech',
        'cgpa': 3.94,
        'university_id': 'DS-2020-005',
        'github_username': 'karim-datascience',
        'github_score': 91,
        'linkedin_score': 85,
        'trust_score': 93.5,
        'profile_complete_score': 0.98,
        'activity_score': 95,
        'skills': ['Python', 'TensorFlow', 'Machine Learning', 'Data Science', 'Pandas', 'NumPy', 'SQL', 'Tableau', 'AWS', 'Docker', 'Kubernetes'],
        'experience': [
            {'company': 'DataMinds BD', 'role': 'Junior Data Scientist', 'start': date(2022,7,1), 'end': date(2023,6,30)},
            {'company': 'ShopUp', 'role': 'ML Engineer Intern', 'start': date(2023,7,1), 'end': date(2024,1,31)},
        ],
        'projects': [
            {'title': 'NLP Sentiment Analyzer', 'desc': 'BERT-based Bengali sentiment analysis', 'tech': ['Python','TensorFlow','NLP']},
            {'title': 'Demand Forecasting', 'desc': 'LSTM time-series sales forecasting', 'tech': ['Python','Pandas','ML']},
            {'title': 'Customer Churn Predictor', 'desc': 'XGBoost churn prediction model', 'tech': ['Python','AWS','Docker']},
            {'title': 'Real-time Dashboard', 'desc': 'Live analytics with Tableau', 'tech': ['Tableau','SQL','Python']},
        ],
        'tag': 'Data Science (Exceptional Profile)',
    },
]

COMPANIES_DATA = [
    {
        'name': 'TechCorp Bangladesh',
        'email': 'test_techcorp@demo.com',
        'industry': 'Software & Technology',
        'size': '201-500',
        'description': 'Leading software development company building enterprise solutions.',
        'tag': 'Tech Company',
    },
    {
        'name': 'DataMinds Analytics',
        'email': 'test_dataminds@demo.com',
        'industry': 'Data Analytics & AI',
        'size': '51-200',
        'description': 'AI-first analytics company specialising in ML solutions.',
        'tag': 'AI/Data Company',
    },
    {
        'name': 'GreenTech Engineering',
        'email': 'test_greentech@demo.com',
        'industry': 'Engineering & Manufacturing',
        'size': '501-1000',
        'description': 'Industrial engineering firm specialising in embedded systems.',
        'tag': 'Engineering Company',
    },
]

JOBS_DATA = [
    {
        'company_idx': 0,
        'title': 'Senior Django Backend Developer',
        'department': 'Engineering',
        'job_type': 'full_time',
        'location': 'Dhaka',
        'min_cgpa': 3.0,
        'salary_range': {'min': 60000, 'max': 90000, 'currency': 'BDT'},
        'description': 'Build scalable Django APIs for our enterprise SaaS platform.',
        'skills': ['Python', 'Django', 'PostgreSQL', 'Docker', 'REST API', 'Git'],
    },
    {
        'company_idx': 1,
        'title': 'Machine Learning Engineer',
        'department': 'Data Science',
        'job_type': 'full_time',
        'location': 'Dhaka (Hybrid)',
        'min_cgpa': 3.5,
        'salary_range': {'min': 80000, 'max': 120000, 'currency': 'BDT'},
        'description': 'Design and deploy ML models for real-time analytics pipelines.',
        'skills': ['Python', 'Machine Learning', 'TensorFlow', 'SQL', 'AWS', 'Docker'],
    },
    {
        'company_idx': 1,
        'title': 'Data Analyst',
        'department': 'Analytics',
        'job_type': 'full_time',
        'location': 'Dhaka',
        'min_cgpa': 3.0,
        'salary_range': {'min': 40000, 'max': 65000, 'currency': 'BDT'},
        'description': 'Analyse business data and create Tableau dashboards for stakeholders.',
        'skills': ['SQL', 'Tableau', 'Python', 'Pandas', 'Excel', 'Data Science'],
    },
    {
        'company_idx': 0,
        'title': 'Junior Frontend Developer',
        'department': 'Engineering',
        'job_type': 'full_time',
        'location': 'Dhaka',
        'min_cgpa': 2.5,
        'salary_range': {'min': 25000, 'max': 40000, 'currency': 'BDT'},
        'description': 'Build responsive UIs using React and modern CSS.',
        'skills': ['React', 'JavaScript', 'HTML', 'CSS', 'REST API'],
    },
    {
        'company_idx': 0,
        'title': 'Full Stack Developer',
        'department': 'Engineering',
        'job_type': 'full_time',
        'location': 'Dhaka',
        'min_cgpa': 3.2,
        'salary_range': {'min': 55000, 'max': 85000, 'currency': 'BDT'},
        'description': 'Work across the full stack — Django backend + React frontend.',
        'skills': ['Python', 'Django', 'React', 'JavaScript', 'SQL', 'Git', 'Docker'],
    },
    {
        'company_idx': 2,
        'title': 'Embedded Systems Engineer',
        'department': 'R&D',
        'job_type': 'full_time',
        'location': 'Chittagong',
        'min_cgpa': 3.0,
        'salary_range': {'min': 45000, 'max': 70000, 'currency': 'BDT'},
        'description': 'Design firmware and embedded systems for industrial IoT devices.',
        'skills': ['Arduino', 'C++', 'MATLAB', 'Circuit Design', 'Embedded Systems'],
    },
    {
        'company_idx': 0,
        'title': 'Marketing Manager',
        'department': 'Marketing',
        'job_type': 'full_time',
        'location': 'Dhaka',
        'min_cgpa': 3.0,
        'salary_range': {'min': 50000, 'max': 75000, 'currency': 'BDT'},
        'description': 'Lead digital marketing campaigns and growth strategy.',
        'skills': ['Marketing', 'Sales', 'Communication', 'Leadership', 'Excel'],
    },
    {
        'company_idx': 1,
        'title': 'Business Analyst (AI Products)',
        'department': 'Product',
        'job_type': 'full_time',
        'location': 'Dhaka',
        'min_cgpa': 3.0,
        'salary_range': {'min': 45000, 'max': 70000, 'currency': 'BDT'},
        'description': 'Bridge business requirements and AI product features.',
        'skills': ['Business Analysis', 'SQL', 'Excel', 'Communication', 'Project Management', 'Power BI'],
    },
]


class Command(BaseCommand):
    help = 'Create test data (5 students, 3 companies, 8 jobs) for poster presentation testing'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete existing test data first')

    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write('🗑️  Flushing old test data...')
            Student.objects.filter(email__contains='test_').delete()
            Company.objects.filter(email__contains='test_').delete()
            self.stdout.write(self.style.WARNING('   Old test data removed.'))

        self.stdout.write('\n' + '='*60)
        self.stdout.write('  AI TALENT MATCH — TEST DATA CREATOR')
        self.stdout.write('='*60)

        # ── Skills ──────────────────────────────────────────────────
        self.stdout.write('\n📌 Creating skills...')
        skills_map = {}
        for skill_name in SKILLS_DATA:
            skill, _ = Skill.objects.get_or_create(name=skill_name)
            skills_map[skill_name] = skill
        self.stdout.write(self.style.SUCCESS(f'   ✓ {len(skills_map)} skills ready'))

        # ── Companies ────────────────────────────────────────────────
        self.stdout.write('\n🏢 Creating companies...')
        companies = []
        for c_data in COMPANIES_DATA:
            company, created = Company.objects.get_or_create(
                email=c_data['email'],
                defaults={
                    'name': c_data['name'],
                    'industry': c_data['industry'],
                    'size': c_data['size'],
                    'description': c_data['description'],
                }
            )
            if created:
                company.set_password('TestPass123!')
                company.save()
            companies.append(company)
            status = '✓ Created' if created else '→ Already exists'
            self.stdout.write(f'   {status}: {company.name} ({c_data["tag"]})')

        # ── Jobs ─────────────────────────────────────────────────────
        DEPT_CAT_MAP = {
            'Engineering': 'tech', 'Data Science': 'tech', 'Analytics': 'tech',
            'R&D': 'engineering', 'Marketing': 'business', 'Product': 'business',
        }
        self.stdout.write('\n💼 Creating jobs...')
        jobs = []
        for j_data in JOBS_DATA:
            company = companies[j_data['company_idx']]
            dept_cat = DEPT_CAT_MAP.get(j_data.get('department', ''), 'any')
            # Use update_or_create so department_category is always in sync
            job, created = Job.objects.update_or_create(
                title=j_data['title'],
                company=company,
                defaults={
                    'job_type': j_data['job_type'],
                    'location': j_data['location'],
                    'min_cgpa': j_data['min_cgpa'],
                    'salary_range': j_data['salary_range'],
                    'description': j_data['description'],
                    'department_category': dept_cat,
                    'status': 'active',
                }
            )
            # Always sync required skills using set() so re-running this command
            # restores the EXACT canonical skill list (removing any contamination
            # added by other scripts such as create_synthetic_dataset.py).
            job.required_skills.set(
                [skills_map[sn] for sn in j_data['skills'] if sn in skills_map]
            )
            jobs.append(job)
            status = '✓ Created' if created else '↺ Updated'
            self.stdout.write(f'   {status}: {job.title} @ {company.name} [dept={dept_cat}]')

        # ── Students ─────────────────────────────────────────────────
        self.stdout.write('\n🎓 Creating students...')
        students = []
        for s_data in STUDENTS_DATA:
            student, created = Student.objects.get_or_create(
                email=s_data['email'],
                defaults={
                    'name': s_data['name'],
                    'department': s_data['department'],
                    'department_category': s_data['department_category'],
                    'cgpa': s_data['cgpa'],
                    'university_id': s_data['university_id'],
                    'github_username': s_data.get('github_username', ''),
                    'github_score': s_data.get('github_score', 0),
                    'linkedin_score': s_data.get('linkedin_score', 0),
                    'trust_score': s_data['trust_score'],
                    'profile_complete_score': s_data['profile_complete_score'],
                    'activity_score': s_data['activity_score'],
                    'graduation_date': date(2025, 12, 31),
                }
            )
            if created:
                student.set_password('TestPass123!')
                student.save()

            # Always sync skills (add missing ones; never remove existing ones)
            if True:
                for skill_name in s_data['skills']:
                    if skill_name in skills_map:
                        StudentSkill.objects.get_or_create(
                            student=student,
                            skill=skills_map[skill_name],
                            defaults={'proficiency_level': 'Intermediate', 'source': 'manual'}
                        )

            if created:
                # Experience
                for exp in s_data.get('experience', []):
                    WorkExperience.objects.get_or_create(
                        student=student,
                        company_name=exp['company'],
                        role=exp['role'],
                        defaults={
                            'start_date': exp['start'],
                            'end_date': exp.get('end'),
                            'is_current': exp.get('end') is None,
                        }
                    )

                # Projects
                for proj in s_data.get('projects', []):
                    p_obj, p_created = Project.objects.get_or_create(
                        student=student,
                        title=proj['title'],
                        defaults={'description': proj['desc']},
                    )
                    if p_created:
                        for tech_name in proj.get('tech', []):
                            tech_skill, _ = Skill.objects.get_or_create(name=tech_name)
                            p_obj.tech_stack.add(tech_skill)

            students.append(student)
            status = '✓ Created' if created else '→ Already exists'
            self.stdout.write(f'   {status}: {student.name} [{s_data["tag"]}]')
            self.stdout.write(f'          Trust: {student.trust_score} | CGPA: {student.cgpa} | Skills: {len(s_data["skills"])}')

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'\n✅ TEST DATA READY'))
        self.stdout.write(f'   Students  : {len(students)}')
        self.stdout.write(f'   Companies : {len(companies)}')
        self.stdout.write(f'   Jobs      : {len(jobs)}')
        self.stdout.write(f'   Skills    : {len(skills_map)}')
        self.stdout.write('\n▶  Now run: python manage.py run_poster_tests\n')
