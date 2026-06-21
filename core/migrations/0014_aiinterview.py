import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_recruitment_agent_run'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIInterview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('questions',       models.JSONField(default=list)),
                ('answers',         models.JSONField(default=list)),
                ('interview_score', models.FloatField(blank=True, null=True)),
                ('combined_score',  models.FloatField(blank=True, null=True)),
                ('status',          models.CharField(
                    choices=[
                        ('pending',     'Pending — link sent, not started'),
                        ('in_progress', 'In Progress'),
                        ('completed',   'Completed'),
                    ],
                    default='pending', max_length=15
                )),
                ('token',        models.CharField(max_length=64, unique=True)),
                ('email_sent',   models.BooleanField(default=False)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('application', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ai_interviews', to='core.application'
                )),
                ('agent_run', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='interviews', to='core.recruitmentagentrun'
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
