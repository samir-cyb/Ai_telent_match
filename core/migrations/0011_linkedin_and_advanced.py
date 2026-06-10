from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_department_based_profiles'),
    ]

    operations = [
        # ---- Student: LinkedIn PDF verification fields ----
        migrations.AddField(
            model_name='student',
            name='linkedin_pdf',
            field=models.FileField(blank=True, null=True, upload_to='linkedin_pdfs/'),
        ),
        migrations.AddField(
            model_name='student',
            name='linkedin_score',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='student',
            name='linkedin_parsed_data',
            field=models.JSONField(default=dict),
        ),

        # ---- StudentSkill: cross-validation + source tracking ----
        migrations.AddField(
            model_name='studentskill',
            name='cross_validated',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='studentskill',
            name='source',
            field=models.CharField(
                choices=[
                    ('cv', 'CV Upload'),
                    ('linkedin', 'LinkedIn PDF'),
                    ('manual', 'Manually Added'),
                ],
                default='manual',
                max_length=20,
            ),
        ),
    ]
