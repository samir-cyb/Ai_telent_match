from core.models import LeaderboardEntry, Student
from django.db import transaction

# Actions that can be awarded multiple times (once per unique_key)
REPEATABLE_ACTIONS = {'assessment_passed', 'shortlisted', 'hired'}

POINTS_MAP = {
    'profile_complete':   50,
    'add_skill':          10,
    'add_project':        10,
    'assessment_passed':  25,
    'shortlisted':        15,
    'hired':              50,
    'referral':           20,
}


@transaction.atomic
def award_points(student, action, unique_key=None):
    """
    Award points to a student for an action.

    For repeatable actions (assessment_passed, shortlisted, hired), pass
    unique_key (e.g. str(application.id)) so the same event isn't double-counted
    but different events are all counted.

    Returns the new total_points value.
    """
    points = POINTS_MAP.get(action, 0)
    if points == 0:
        return 0

    Student.objects.select_for_update().get(pk=student.pk)
    entry, _ = LeaderboardEntry.objects.get_or_create(
        student=student,
        defaults={'university': student.university_id or ''}
    )

    entry = LeaderboardEntry.objects.select_for_update().get(pk=entry.pk)

    # Build the tracking key stored in awarded_actions list
    if action in REPEATABLE_ACTIONS and unique_key:
        tracking_key = f"{action}:{unique_key}"
    else:
        tracking_key = action   # one-time actions use bare name

    if tracking_key in entry.awarded_actions:
        return entry.total_points   # already counted

    entry.awarded_actions.append(tracking_key)
    entry.total_points += points
    if not entry.university:
        entry.university = student.university_id or ''
    entry.save()
    return entry.total_points
