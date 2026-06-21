import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_aifeedbacklog_rl_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecruitmentAgentRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('triggered_by', models.CharField(
                    choices=[('auto', 'Auto — triggered on apply'), ('manual', 'Manual — company re-run')],
                    default='auto', max_length=10
                )),
                ('status', models.CharField(
                    choices=[('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')],
                    default='running', max_length=10
                )),
                ('score', models.FloatField(default=0.0)),
                ('decision', models.CharField(
                    choices=[('shortlist', 'Shortlist'), ('reject', 'Reject'), ('review', 'Manual Review')],
                    default='review', max_length=10
                )),
                ('confidence', models.CharField(default='LOW', max_length=10)),
                ('reasoning_steps', models.JSONField(default=list)),
                ('fit_report', models.JSONField(default=dict)),
                ('weights_used', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='agent_runs',
                    to='core.application'
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
