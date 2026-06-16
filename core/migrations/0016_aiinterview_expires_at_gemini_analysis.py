from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_interview_location_contact'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiinterview',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='aiinterview',
            name='gemini_analysis',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
