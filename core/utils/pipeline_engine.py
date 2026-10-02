"""
Pipeline Engine — Auto Hiring Pipeline

Stages:
  sort_review   → AI scored all applicants, company reviews top N
  vetting       → Vetting tests sent to approved candidates, deadline running
  vetting_review→ Deadline passed, company approves who goes to interview
  interviewing  → AI interviews sent, deadline running
  completed     → Final scores computed, report ready

Score formula: Match×0.30 + Vetting×0.40 + Interview×0.30
"""

import logging
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)

FINAL_WEIGHTS = {'match': 0.30, 'vetting': 0.40, 'interview': 0.30}


@transaction.atomic
def run_sort(pipeline):
    """Score all applications for the job and create PipelineCandidate records."""
    from core.models import PipelineRun
    PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
    pipeline.refresh_from_db()
    from core.models import Application, PipelineCandidate
    from core.utils.ai_engine import AIMatchingEngine

    applications = Application.objects.filter(
        job=pipeline.job
    ).select_related('student', 'job', 'job__company').exclude(status='rejected')

    engine = AIMatchingEngine(company=pipeline.job.company, job=pipeline.job)
    scored = []
    for app in applications:
        try:
            score, _ = engine.calculate_match(app.student, pipeline.job, save_explanation=False)
        except Exception:
            score = float(app.match_score or 0)
        scored.append((app, round(score, 2)))

    scored.sort(key=lambda x: -x[1])

    bulk = []
    for rank, (app, score) in enumerate(scored, 1):
        bulk.append(PipelineCandidate(
            pipeline=pipeline,
            application=app,
            sort_score=score,
            sort_rank=rank,
            stage='sort',
        ))
    pipeline.candidates.all().delete()
    PipelineCandidate.objects.bulk_create(bulk)
    pipeline.stage = 'sort_review'
    pipeline.save(update_fields=['stage', 'updated_at'])
    return len(bulk)


@transaction.atomic
def approve_sort_and_send_vetting(pipeline, approved_application_ids, vetting_deadline,
                                   topic='', force_type='', keywords=''):
    """
    Company approved the sorted list.
    - Eliminate non-approved candidates
    - Auto-generate vetting test if not exists (or regenerate if topic provided)
    - Create VettingSession for each approved candidate
    - Send notification to each student
    """
    from core.models import PipelineRun
    PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
    pipeline.refresh_from_db()
    from core.models import PipelineCandidate, Notification
    from vetting.models import VettingChallenge, VettingSession

    # Eliminate non-approved
    pipeline.candidates.exclude(
        application_id__in=approved_application_ids
    ).update(stage='eliminated', eliminated_at_stage='sort')

    # Ensure VettingChallenge exists for this job (regenerate if topic/type given)
    challenge = _ensure_vetting_challenge(pipeline.job, topic=topic, force_type=force_type, keywords=keywords)

    # Create VettingSession for each approved candidate
    window_start = timezone.now()
    window_end = vetting_deadline

    approved_candidates = pipeline.candidates.filter(
        application_id__in=approved_application_ids
    ).select_related('application__student')

    for candidate in approved_candidates:
        app = candidate.application
        student = app.student

        session, created = VettingSession.objects.get_or_create(
            challenge=challenge,
            application=app,
            defaults={
                'student': student,
                'token_expires_at': vetting_deadline,
                'window_start': window_start,
                'window_end': window_end,
                'max_duration_minutes': challenge.time_limit_minutes,
                'status': 'pending',
            }
        )

        candidate.stage = 'vetting'
        candidate.save(update_fields=['stage', 'updated_at'])

        # Notify student
        test_url = f"/vetting/test/{session.access_token}/"
        Notification.objects.create(
            user_id=student.id,
            user_type='student',
            type='pipeline_vetting',
            title=f'Vetting Test — {pipeline.job.title}',
            message=(
                f'You have been selected for the vetting test for "{pipeline.job.title}" '
                f'at {pipeline.job.company.name}. '
                f'Deadline: {vetting_deadline.strftime("%d %b %Y, %I:%M %p")}.'
            ),
            data={
                'pipeline_id': str(pipeline.id),
                'job_id': str(pipeline.job.id),
                'job_title': pipeline.job.title,
                'test_url': test_url,
                'vetting_session_id': str(session.id),
                'deadline': vetting_deadline.isoformat(),
            }
        )

    pipeline.vetting_deadline = vetting_deadline
    pipeline.stage = 'vetting'
    pipeline.save(update_fields=['stage', 'vetting_deadline', 'updated_at'])

    # Notify company
    Notification.objects.create(
        user_id=pipeline.job.company.id,
        user_type='company',
        type='pipeline_update',
        title=f'Vetting Tests Sent — {pipeline.job.title}',
        message=f'{len(approved_application_ids)} candidates have been sent the vetting test. Deadline: {vetting_deadline.strftime("%d %b %Y")}.',
        data={'pipeline_id': str(pipeline.id), 'job_id': str(pipeline.job.id)}
    )


@transaction.atomic
def collect_vetting_scores_and_review(pipeline):
    """
    Called when vetting deadline has passed.
    Collect VettingResult scores, rank candidates, move to vetting_review stage.
    """
    from core.models import PipelineRun
    PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
    pipeline.refresh_from_db()
    from core.models import PipelineCandidate, Notification
    from vetting.models import VettingResult

    vetting_candidates = pipeline.candidates.filter(
        stage='vetting'
    ).select_related('application')

    scored = []
    for candidate in vetting_candidates:
        try:
            result = VettingResult.objects.get(application=candidate.application)
            score = float(result.final_score)
        except VettingResult.DoesNotExist:
            score = None  # didn't submit
        candidate.vetting_score = score
        candidate.save(update_fields=['vetting_score', 'updated_at'])
        scored.append((candidate, score or 0))

    # Rank by vetting score
    scored.sort(key=lambda x: -x[1])
    for rank, (candidate, _) in enumerate(scored, 1):
        candidate.vetting_rank = rank
        candidate.save(update_fields=['vetting_rank', 'updated_at'])

    pipeline.stage = 'vetting_review'
    pipeline.save(update_fields=['stage', 'updated_at'])

    submitted = sum(1 for _, s in scored if s > 0)
    Notification.objects.create(
        user_id=pipeline.job.company.id,
        user_type='company',
        type='pipeline_update',
        title=f'Vetting Complete — {pipeline.job.title}',
        message=f'{submitted} of {len(scored)} candidates submitted the vetting test. Please review and select who advances to AI Interview.',
        data={'pipeline_id': str(pipeline.id), 'job_id': str(pipeline.job.id), 'stage': 'vetting_review'}
    )


@transaction.atomic
def approve_vetting_and_send_interviews(pipeline, approved_application_ids, interview_deadline):
    """
    Company approved vetting results.
    - Eliminate non-approved
    - Create AIInterview for each approved candidate
    - Send notifications
    """
    from core.models import PipelineRun
    PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
    pipeline.refresh_from_db()
    from core.models import PipelineCandidate, AIInterview, Notification
    from core.utils import interview_generator as _ig
    import secrets as _secrets

    # Eliminate non-approved from vetting stage
    pipeline.candidates.filter(stage='vetting').exclude(
        application_id__in=approved_application_ids
    ).update(stage='eliminated', eliminated_at_stage='vetting')

    approved_candidates = pipeline.candidates.filter(
        application_id__in=approved_application_ids
    ).select_related('application__student', 'application__job')

    for candidate in approved_candidates:
        app = candidate.application
        student = app.student

        # Generate AI interview
        try:
            questions = _ig.generate_questions(student, app.job)
        except Exception as e:
            logger.error(f"Pipeline: interview gen failed for {student.name}: {e}")
            raise RuntimeError('Interview generation failed; pipeline state is preserved.') from e
        if not questions:
            raise RuntimeError('Interview provider returned no questions; retry after checking configuration.')

        token = _secrets.token_urlsafe(32)
        # Agent runs can legitimately create several interviews per application.
        # Reuse its latest interview rather than assuming a one-to-one relation.
        interview = AIInterview.objects.filter(application=app).order_by('-created_at').first()
        if interview is None:
            interview = AIInterview.objects.create(application=app, token=token, status='pending',
                                                   questions=questions, expires_at=interview_deadline)
        else:
            interview.questions = questions
            interview.expires_at = interview_deadline
            interview.status = 'pending'
            interview.answers = []
            interview.interview_score = None
            interview.combined_score = None
            interview.completed_at = None
            interview.gemini_analysis = None
            interview.save(update_fields=['questions', 'expires_at', 'status', 'answers',
                                         'interview_score', 'combined_score', 'completed_at', 'gemini_analysis'])

        candidate.stage = 'interview'
        candidate.save(update_fields=['stage', 'updated_at'])

        from django.urls import reverse
        interview_url = reverse('candidate_interview', kwargs={'token': interview.token})
        Notification.objects.create(
            user_id=student.id,
            user_type='student',
            type='pipeline_interview',
            title=f'AI Interview — {pipeline.job.title}',
            message=(
                f'You passed the vetting test! Complete your AI interview for '
                f'"{pipeline.job.title}" at {pipeline.job.company.name}. '
                f'Deadline: {interview_deadline.strftime("%d %b %Y, %I:%M %p")}.'
            ),
            data={
                'pipeline_id': str(pipeline.id),
                'job_id': str(pipeline.job.id),
                'interview_token': interview.token,
                'interview_url': interview_url,
                'deadline': interview_deadline.isoformat(),
            }
        )

    pipeline.interview_deadline = interview_deadline
    pipeline.stage = 'interviewing'
    pipeline.save(update_fields=['stage', 'interview_deadline', 'updated_at'])

    Notification.objects.create(
        user_id=pipeline.job.company.id,
        user_type='company',
        type='pipeline_update',
        title=f'AI Interviews Sent — {pipeline.job.title}',
        message=f'{len(approved_application_ids)} candidates have been sent AI interviews. Deadline: {interview_deadline.strftime("%d %b %Y")}.',
        data={'pipeline_id': str(pipeline.id), 'job_id': str(pipeline.job.id)}
    )


@transaction.atomic
def finalize_pipeline(pipeline):
    """
    Called when interview deadline passes.
    Collect interview scores, compute final scores (Match×0.30 + Vetting×0.40 + Interview×0.30).
    """
    from core.models import PipelineRun
    PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
    pipeline.refresh_from_db()
    from core.models import PipelineCandidate, AIInterview, Notification

    interview_candidates = pipeline.candidates.filter(stage='interview')

    scored = []
    for candidate in interview_candidates:
        try:
            interview = AIInterview.objects.get(application=candidate.application)
            i_score = float(interview.interview_score or 0)
        except AIInterview.DoesNotExist:
            i_score = 0

        candidate.interview_score = i_score

        # Final score = Match×0.30 + Vetting×0.40 + Interview×0.30
        match_s = candidate.sort_score or 0
        vetting_s = candidate.vetting_score or 0
        final = round(match_s * 0.30 + vetting_s * 0.40 + i_score * 0.30, 2)
        candidate.final_score = final
        candidate.stage = 'final'
        candidate.save(update_fields=['interview_score', 'final_score', 'stage', 'updated_at'])
        scored.append((candidate, final))

    # Rank by final score
    scored.sort(key=lambda x: -x[1])
    for rank, (candidate, _) in enumerate(scored, 1):
        candidate.interview_rank = rank
        candidate.save(update_fields=['interview_rank', 'updated_at'])

    pipeline.stage = 'completed'
    pipeline.save(update_fields=['stage', 'updated_at'])

    top_candidate = scored[0][0].application.student.name if scored else 'N/A'
    Notification.objects.create(
        user_id=pipeline.job.company.id,
        user_type='company',
        type='pipeline_complete',
        title=f'Pipeline Complete — {pipeline.job.title}',
        message=f'All {len(scored)} candidates have been evaluated. Top candidate: {top_candidate}. View the final report now.',
        data={'pipeline_id': str(pipeline.id), 'job_id': str(pipeline.job.id), 'stage': 'completed'}
    )


@transaction.atomic
def check_and_advance_deadlines(pipeline):
    """
    Call this on every pipeline page load.
    Automatically advances stages when deadlines pass.
    """
    from core.models import PipelineRun
    PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
    pipeline.refresh_from_db()
    now = timezone.now()

    if pipeline.stage == 'vetting' and pipeline.vetting_deadline and now >= pipeline.vetting_deadline:
        collect_vetting_scores_and_review(pipeline)

    elif pipeline.stage == 'interviewing' and pipeline.interview_deadline and now >= pipeline.interview_deadline:
        finalize_pipeline(pipeline)


def get_pipeline_report(pipeline):
    """Return full report data for the pipeline."""
    from core.models import AIInterview
    from vetting.models import VettingResult

    candidates = pipeline.candidates.select_related(
        'application__student'
    ).order_by('sort_rank')

    report = []
    for c in candidates:
        student = c.application.student
        vetting_details = None
        interview_details = None

        try:
            vr = VettingResult.objects.get(application=c.application)
            vetting_details = {
                'score': float(vr.final_score),
                'passed': vr.passed,
                'ai_feedback': vr.ai_feedback[:200] if vr.ai_feedback else None,
            }
        except VettingResult.DoesNotExist:
            pass

        try:
            ai = AIInterview.objects.get(application=c.application)
            interview_details = {
                'score': float(ai.interview_score or 0),
                'status': ai.status,
            }
        except AIInterview.DoesNotExist:
            pass

        report.append({
            'candidate_id': str(c.id),
            'application_id': str(c.application.id),
            'student_id': str(student.id),
            'student_name': student.name,
            'student_email': student.email,
            'department': student.department or '',
            'cgpa': float(student.cgpa or 0),
            'stage': c.stage,
            'eliminated_at': c.eliminated_at_stage,
            'sort_score': c.sort_score,
            'sort_rank': c.sort_rank,
            'vetting_score': c.vetting_score,
            'vetting_rank': c.vetting_rank,
            'interview_score': c.interview_score,
            'interview_rank': c.interview_rank,
            'final_score': c.final_score,
            'vetting_details': vetting_details,
            'interview_details': interview_details,
        })

    return {
        'pipeline_id': str(pipeline.id),
        'job_title': pipeline.job.title,
        'stage': pipeline.stage,
        'total_candidates': len(report),
        'candidates': report,
    }


_TECH_KEYWORDS = {
    'python', 'django', 'flask', 'fastapi', 'java', 'kotlin', 'javascript', 'typescript',
    'react', 'vue', 'angular', 'node', 'nodejs', 'express', 'php', 'laravel',
    'c++', 'c#', '.net', 'dotnet', 'go', 'golang', 'rust', 'swift', 'dart', 'flutter',
    'ruby', 'rails', 'sql', 'mysql', 'postgres', 'mongodb', 'redis', 'elasticsearch',
    'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'devops', 'backend', 'frontend',
    'fullstack', 'full-stack', 'full stack', 'software', 'developer', 'engineer',
    'programmer', 'coding', 'data science', 'machine learning', 'ai', 'ml', 'nlp',
    'api', 'rest', 'graphql', 'microservice', 'cloud', 'linux', 'android', 'ios',
    'cybersecurity', 'blockchain', 'web developer', 'mobile developer', 'data analyst',
    'data engineer', 'sysadmin', 'network engineer', 'database', 'algorithm',
}


def _job_is_tech(job):
    """Return True if the job is a technical/coding role."""
    dept = getattr(job, 'department_category', 'any') or 'any'
    if dept in ('tech', 'engineering'):
        return True
    title_lower = (job.title or '').lower()
    desc_lower  = (job.description or '')[:300].lower()
    # Check title and first 300 chars of description
    for kw in _TECH_KEYWORDS:
        if kw in title_lower or kw in desc_lower:
            return True
    # Also check required skills
    skill_names = [s.name.lower() for s in job.required_skills.all()]
    tech_skills = {'python', 'java', 'javascript', 'sql', 'django', 'react', 'nodejs',
                   'c++', 'c#', 'go', 'rust', 'swift', 'docker', 'kubernetes'}
    if any(s in tech_skills for s in skill_names):
        return True
    return False


def _challenge_is_bad(challenge):
    """Return True if the existing challenge was generated with bad/empty content."""
    if challenge.assessment_type == 'mcq_written':
        qs = challenge.mcq_questions or []
        if len(qs) == 0:
            return True
        # Detect all-identical questions (fallback generated same Q N times)
        q_texts = [q.get('question', '') for q in qs]
        if len(set(q_texts)) <= 1 and len(q_texts) > 1:
            return True
        return False
    elif challenge.assessment_type == 'coding':
        if not challenge.test_cases or len(challenge.test_cases) == 0:
            return True
        if not challenge.description or len(challenge.description) < 30:
            return True
    return False


def _ensure_vetting_challenge(job, topic='', force_type='', keywords=''):
    """
    Auto-generate VettingChallenge for job.
    - If topic/force_type provided, always regenerate fresh (delete old)
    - If existing is bad (empty or identical questions), regenerate
    - Otherwise return existing
    """
    from vetting.models import VettingChallenge
    from vetting.services import QuestionGenerator

    try:
        existing = job.vetting_challenge
        # If company specified a new topic, always regenerate for fresh questions
        if topic:
            logger.info(f"Pipeline: topic '{topic}' provided — forcing fresh challenge for '{job.title}'")
            existing.delete()
        elif _challenge_is_bad(existing):
            logger.info(f"Pipeline: deleting bad challenge for job '{job.title}', regenerating")
            existing.delete()
        else:
            return existing
    except VettingChallenge.DoesNotExist:
        pass

    # Determine assessment type
    if force_type in ('coding', 'mcq_written'):
        is_tech = (force_type == 'coding')
    else:
        is_tech = _job_is_tech(job)

    dept = getattr(job, 'department_category', 'any') or 'any'
    assessment_type = 'coding' if is_tech else 'mcq_written'
    effective_topic = topic or job.title  # use job title as fallback topic
    logger.info(f"Pipeline: generating {'CODING' if is_tech else 'MCQ'} challenge for '{job.title}' topic='{effective_topic}'")

    generator = QuestionGenerator()
    try:
        if is_tech:
            data = generator.generate_challenge(job, 'medium', dept,
                                                topic=effective_topic, keywords=keywords)
            challenge = VettingChallenge.objects.create(
                job=job,
                title=data['title'],
                description=data['description'],
                starter_code=data['starter_code'],
                test_cases=data['test_cases'],
                language=data.get('language', 'python'),
                difficulty='medium',
                assessment_type='coding',
                department_category=dept,
                skill_tags=data.get('skill_tags', []),
                topic_focus=effective_topic,
                is_active=True,
            )
        else:
            data = generator.generate_mcq_written(job, 'medium', dept,
                                                   topic=effective_topic, keywords=keywords,
                                                   mcq_count=5, written_count=2)
            challenge = VettingChallenge.objects.create(
                job=job,
                title=data['title'],
                description=data.get('instructions', ''),
                starter_code='',
                test_cases=[],
                language='none',
                difficulty='medium',
                assessment_type='mcq_written',
                department_category=dept,
                mcq_questions=data.get('questions', []),
                topic_focus=effective_topic,
                is_active=True,
            )
        if _challenge_is_bad(challenge):
            raise RuntimeError('Assessment provider returned empty questions.')
        return challenge
    except Exception as e:
        logger.error(f"Pipeline: auto-generate vetting challenge failed: {e}")
        # Fallback: create minimal placeholder
        raise RuntimeError('Assessment generation failed; previous pipeline data is preserved.') from e
