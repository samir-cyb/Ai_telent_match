from django.core.management.base import BaseCommand
from django.db.models import Q
from datetime import datetime, timedelta

from core.models import (
    Student, Job, Application, MatchExplanation, 
    Notification, FraudFlag, StudentBehaviorLog
)
from core.utils.ai_engine import AIMatchingEngine, ABTestFramework
from core.utils.fraud_detector import FraudDetectionEngine


class Command(BaseCommand):
    help = 'Run daily batch matching and analytics updates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--full-refresh',
            action='store_true',
            help='Run full refresh for all students, not just recent updates',
        )
        parser.add_argument(
            '--fraud-only',
            action='store_true',
            help='Run only fraud detection',
        )
        parser.add_argument(
            '--trust-only',
            action='store_true',
            help='Run only trust score updates',
        )

    def handle(self, *args, **kwargs):
        full_refresh = kwargs['full_refresh']
        fraud_only = kwargs['fraud_only']
        trust_only = kwargs['trust_only']
        
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("Starting Daily Batch Processing"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        
        # 1. Update all student trust scores
        if not fraud_only:
            self.update_trust_scores(full_refresh)
        
        # 2. Recalculate match scores for pending applications
        if not fraud_only and not trust_only:
            self.recalculate_match_scores()
        
        # 3. Auto-shortlist high-scoring candidates
        if not fraud_only and not trust_only:
            self.auto_shortlist_candidates()
        
        # 4. Fraud detection sweep
        if not trust_only:
            self.run_fraud_detection(full_refresh)
        
        # 5. Update job competition metrics
        if not fraud_only and not trust_only:
            self.update_job_metrics()
        
        # 6. Generate A/B test reports
        if not fraud_only and not trust_only:
            self.generate_ab_test_report()
        
        # 7. Send notifications for important updates
        if not fraud_only and not trust_only:
            self.send_daily_notifications()
        
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS('Daily batch completed successfully'))
        self.stdout.write(self.style.SUCCESS("=" * 50))
    
    def update_trust_scores(self, full_refresh=False):
        """Update all student trust scores"""
        self.stdout.write(self.style.HTTP_INFO("\n📊 Updating trust scores..."))
        
        if full_refresh:
            students = Student.objects.all()
        else:
            # Only update students who logged in recently or have pending updates
            students = Student.objects.filter(
                Q(last_login__gte=datetime.now() - timedelta(days=7)) |
                Q(updated_at__gte=datetime.now() - timedelta(days=1))
            )
        
        updated = 0
        for student in students:
            old_score = student.trust_score
            student.calculate_trust_score()
            
            # Flag significant changes
            if abs(student.trust_score - old_score) > 10:
                self.stdout.write(
                    f"  ⚠️  {student.name}: Trust score changed from {old_score:.1f} to {student.trust_score:.1f}"
                )
            updated += 1
        
        self.stdout.write(self.style.SUCCESS(f"✅ Updated {updated} student trust scores"))
    
    def recalculate_match_scores(self):
        """Recalculate match scores for pending applications"""
        self.stdout.write(self.style.HTTP_INFO("\n🔄 Recalculating match scores..."))
        
        pending_apps = Application.objects.filter(status='applied')
        updated = 0
        
        for app in pending_apps:
            engine = AIMatchingEngine(app.job.company)
            new_score, explanation = engine.calculate_match(app.student, app.job)
            
            # Update application
            app.match_score = new_score
            app.save()
            
            # Update or create explanation
            MatchExplanation.objects.update_or_create(
                application=app,
                defaults={
                    'score_breakdown': explanation['breakdown'],
                    'recommendations': explanation['recommendations'],
                    'radar_chart_data': explanation['radar_chart']
                }
            )
            updated += 1
        
        self.stdout.write(self.style.SUCCESS(f"✅ Recalculated {updated} match scores"))
    
    def auto_shortlist_candidates(self):
        """Auto-shortlist high-scoring candidates"""
        self.stdout.write(self.style.HTTP_INFO("\n⭐ Auto-shortlisting top candidates..."))
        
        high_matches = Application.objects.filter(
            status='applied',
            match_score__gte=85
        ).order_by('-match_score')
        
        shortlisted = 0
        for app in high_matches[:50]:  # Limit daily auto-shortlists
            app.status = 'shortlisted'
            app.save()
            
            # Create notification
            Notification.objects.create(
                user_id=app.student.id,
                user_type='student',
                type='auto_shortlisted',
                title=f'Auto-Shortlisted: {app.job.title}',
                message=f'Your high match score ({app.match_score:.1f}%) automatically shortlisted you at {app.job.company.name}',
                data={'job_id': str(app.job.id)}
            )
            shortlisted += 1
        
        self.stdout.write(self.style.SUCCESS(f"✅ Auto-shortlisted {shortlisted} candidates"))
    
    def run_fraud_detection(self, full_refresh=False):
        """Run fraud detection sweep"""
        self.stdout.write(self.style.HTTP_INFO("\n🛡️ Running fraud detection..."))
        
        engine = FraudDetectionEngine()
        
        if full_refresh:
            students = Student.objects.all()
        else:
            students = Student.objects.filter(
                updated_at__gte=datetime.now() - timedelta(days=1)
            )
        
        total_flags = 0
        for student in students:
            flags = engine.analyze_student(student)
            total_flags += len(flags)
        
        # Get statistics
        stats = engine.get_fraud_statistics()
        
        self.stdout.write(self.style.SUCCESS(f"✅ Fraud detection complete"))
        self.stdout.write(f"   - Students analyzed: {students.count()}")
        self.stdout.write(f"   - New flags raised: {total_flags}")
        self.stdout.write(f"   - Total unresolved flags: {stats['total_flags']}")
        self.stdout.write(f"     • High: {stats['by_severity']['high']}")
        self.stdout.write(f"     • Medium: {stats['by_severity']['medium']}")
        self.stdout.write(f"     • Low: {stats['by_severity']['low']}")
    
    def update_job_metrics(self):
        """Update job competition metrics"""
        self.stdout.write(self.style.HTTP_INFO("\n📈 Updating job metrics..."))
        
        active_jobs = Job.objects.filter(status='active')
        updated = 0
        
        for job in active_jobs:
            count = Application.objects.filter(job=job).count()
            if job.total_applicants != count:
                job.total_applicants = count
                job.save()
                updated += 1
        
        self.stdout.write(self.style.SUCCESS(f"✅ Updated metrics for {updated} jobs"))
    
    def generate_ab_test_report(self):
        """Generate A/B testing performance report"""
        self.stdout.write(self.style.HTTP_INFO("\n🧪 Generating A/B test report..."))
        
        results = ABTestFramework.calculate_variant_performance()
        significance = ABTestFramework.get_statistical_significance()
        
        self.stdout.write(self.style.SUCCESS("A/B Test Results:"))
        for variant, data in results.items():
            self.stdout.write(f"  {variant}:")
            self.stdout.write(f"    - Total: {data['total']}, Hired: {data['hired']}")
            self.stdout.write(f"    - Hire Rate: {data['hire_rate']}%")
            self.stdout.write(f"    - Avg Match Score: {data['avg_match_score']}")
        
        # Check for significant improvements
        for variant in ['variant_a', 'variant_b']:
            if significance[variant]['significant']:
                improvement = significance[variant]['improvement']
                self.stdout.write(
                    self.style.SUCCESS(f"  🎉 {variant.upper()} shows significant improvement: {improvement}%")
                )
    
    def send_daily_notifications(self):
        """Send daily summary notifications"""
        self.stdout.write(self.style.HTTP_INFO("\n📧 Sending notifications..."))
        
        # Notify students with new shortlists
        new_shortlists = Application.objects.filter(
            status='shortlisted',
            updated_at__gte=datetime.now() - timedelta(days=1)
        ).exclude(is_auto_applied=True)
        
        for app in new_shortlists:
            Notification.objects.create(
                user_id=app.student.id,
                user_type='student',
                type='shortlisted',
                title=f'Shortlisted for {app.job.title}',
                message=f'Congratulations! You have been shortlisted by {app.job.company.name}',
                data={'job_id': str(app.job.id)}
            )
        
        # Notify companies of new applicants
        new_applications = Application.objects.filter(
            applied_at__gte=datetime.now() - timedelta(days=1)
        )
        
        # Group by company
        company_apps = {}
        for app in new_applications:
            company_id = app.job.company.id
            if company_id not in company_apps:
                company_apps[company_id] = {'company': app.job.company, 'count': 0}
            company_apps[company_id]['count'] += 1
        
        for data in company_apps.values():
            Notification.objects.create(
                user_id=data['company'].id,
                user_type='company',
                type='new_applicants',
                title=f'{data["count"]} New Applicants Today',
                message=f'You received {data["count"]} new applications across your job postings',
                data={}
            )
        
        self.stdout.write(self.style.SUCCESS(f"✅ Sent notifications to {new_shortlists.count()} students and {len(company_apps)} companies"))