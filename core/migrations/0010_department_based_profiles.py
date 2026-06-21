from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_alter_project_description_and_more'),
    ]

    operations = [
        # ---- Student new fields ----
        migrations.AddField(
            model_name='student',
            name='department_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('tech', 'Technology & Software'),
                    ('engineering', 'Engineering'),
                    ('business', 'Business & Management'),
                    ('design', 'Design & Creative'),
                    ('science', 'Science & Research'),
                    ('humanities', 'Humanities & Liberal Arts'),
                    ('any', 'General / Other'),
                ],
                default='any',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='student',
            name='behance_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='student',
            name='certifications',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='student',
            name='eca_activities',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='student',
            name='research_papers',
            field=models.JSONField(default=list),
        ),
        # ---- Job new field ----
        migrations.AddField(
            model_name='job',
            name='department_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('tech', 'Technology & Software'),
                    ('engineering', 'Engineering'),
                    ('business', 'Business & Management'),
                    ('design', 'Design & Creative'),
                    ('science', 'Science & Research'),
                    ('humanities', 'Humanities & Liberal Arts'),
                    ('any', 'Open to All Departments'),
                ],
                default='any',
                max_length=20,
            ),
        ),
        # ---- Skill category choices expansion ----
        # (choices are validated at the Python level; no DB column change needed
        #  for CharField choices in SQLite — the migration still documents the change)
        migrations.AlterField(
            model_name='skill',
            name='category',
            field=models.CharField(
                choices=[
                    ('Frontend', 'Frontend'),
                    ('Backend', 'Backend'),
                    ('AI/ML', 'AI/ML'),
                    ('DevOps', 'DevOps'),
                    ('Data Science', 'Data Science'),
                    ('Mobile', 'Mobile Development'),
                    ('Cybersecurity', 'Cybersecurity'),
                    ('Design', 'Design & Creative'),
                    ('Business', 'Business & Management'),
                    ('Finance', 'Finance & Accounting'),
                    ('Marketing', 'Marketing & Sales'),
                    ('Engineering', 'Engineering'),
                    ('Research', 'Research & Analytics'),
                    ('Communication', 'Communication & Languages'),
                    ('Soft Skills', 'Soft Skills'),
                    ('Uncategorized', 'Uncategorized'),
                ],
                max_length=50,
            ),
        ),
    ]
