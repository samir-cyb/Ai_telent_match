"""
Run this script once to resolve all remaining git merge conflicts
in the template files, keeping YOUR version (HEAD) everywhere.

Usage:
    python fix_conflicts.py
"""
import os

FILES = [
    'templates/student/profile.html',
    'templates/student/dashboard.html',
    'templates/company/dashboard.html',
    'templates/company/applicants.html',
    'templates/base.html',
]

def resolve_keep_head(content):
    result = []
    in_head = False
    in_theirs = False
    for line in content.splitlines(keepends=True):
        if line.startswith('<<<<<<< HEAD'):
            in_head = True
            in_theirs = False
        elif line.startswith('=======') and in_head:
            in_theirs = True
            in_head = False
        elif line.startswith('>>>>>>> ') and in_theirs:
            in_theirs = False
        elif not in_theirs:
            result.append(line)
    return ''.join(result)

base = os.path.dirname(os.path.abspath(__file__))
fixed = 0
for rel in FILES:
    path = os.path.join(base, rel)
    if not os.path.exists(path):
        print(f'  NOT FOUND: {rel}')
        continue
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if '<<<<<<<' not in content:
        print(f'  OK (no conflicts): {rel}')
        continue
    resolved = resolve_keep_head(content)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(resolved)
    print(f'  FIXED: {rel}')
    fixed += 1

print(f'\nDone. {fixed} file(s) cleaned.')
print('Now run: python manage.py makemigrations && python manage.py migrate')
