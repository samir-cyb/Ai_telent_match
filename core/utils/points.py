from core.models import LeaderboardEntry

def award_points(student, action):
    """
    Award points to a student based on action.
    Returns the new total points.
    """
    points_map = {
        'profile_complete': 50,
        'add_skill': 10,
        'add_project': 10,
        'assessment_passed': 25,
        'shortlisted': 15,
        'hired': 50,
        'referral': 20,
    }
    points = points_map.get(action, 0)
    if points == 0:
        return 0

    entry, created = LeaderboardEntry.objects.get_or_create(student=student)
    if action in entry.awarded_actions:
        return entry.total_points  # already awarded

    entry.awarded_actions.append(action)
    entry.total_points += points
    entry.save()
    return entry.total_points