"""
Check and report duplicate student accounts.
Run: python manage.py shell -c "exec(open('check_duplicates.py').read())"
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

from core.models import Student, StudentSkill, Project, Application
from django.db.models import Count

SEP = "=" * 60

print(f"\n{SEP}")
print("  DUPLICATE STUDENT CHECK")
print(SEP)

# Find all students
all_students = Student.objects.all().order_by('id')
for s in all_students:
    skill_count   = StudentSkill.objects.filter(student=s).count()
    project_count = s.projects.count()
    app_count     = Application.objects.filter(student=s).count()
    print(f"\nID={s.id} | Name={s.name} | Email={s.email}")
    print(f"  Skills={skill_count} | Projects={project_count} | Applications={app_count}")
    print(f"  CGPA={s.cgpa} | GitHub={s.github_username or 'none'}")

print(f"\n{SEP}")
print("  SESSION DATA (who is logged in as which student ID)")
print(SEP)
from django.contrib.sessions.models import Session
import json
sessions = Session.objects.all()
for sess in sessions:
    try:
        data = sess.get_decoded()
        student_id = data.get('student_id')
        if student_id:
            print(f"  Session: student_id={student_id} | expires={sess.expire_date}")
    except Exception as e:
        pass

print(f"\n{SEP}")
print("WHAT TO DO:")
print("  If there are 2 accounts with same name/email, one was created by mistake.")
print("  The one with more skills/projects/applications is the 'real' one.")
print("  Run fix_duplicate_student.py to merge and delete the duplicate.")
print(SEP)
