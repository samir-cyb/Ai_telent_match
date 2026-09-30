import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0019_advisor_session'),
    ]
    operations = [
        migrations.CreateModel(
            name='PipelineRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stage', models.CharField(choices=[('sort_review','Awaiting Sort Approval'),('vetting','Vetting In Progress'),('vetting_review','Awaiting Vetting Approval'),('interviewing','AI Interviews In Progress'),('completed','Pipeline Complete'),('cancelled','Cancelled')], default='sort_review', max_length=20)),
                ('sort_top_n', models.IntegerField(default=20)),
                ('vetting_top_n', models.IntegerField(default=10)),
                ('interview_top_n', models.IntegerField(default=5)),
                ('vetting_deadline', models.DateTimeField(blank=True, null=True)),
                ('interview_deadline', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pipeline_runs', to='core.job')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pipeline_runs', to='core.company')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PipelineCandidate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('sort_score', models.FloatField(blank=True, null=True)),
                ('sort_rank', models.IntegerField(blank=True, null=True)),
                ('vetting_score', models.FloatField(blank=True, null=True)),
                ('vetting_rank', models.IntegerField(blank=True, null=True)),
                ('interview_score', models.FloatField(blank=True, null=True)),
                ('interview_rank', models.IntegerField(blank=True, null=True)),
                ('final_score', models.FloatField(blank=True, null=True)),
                ('stage', models.CharField(choices=[('sort','Sorted'),('vetting','In Vetting'),('interview','In Interview'),('final','Final Stage'),('eliminated','Eliminated')], default='sort', max_length=15)),
                ('eliminated_at_stage', models.CharField(blank=True, max_length=15, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('pipeline', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidates', to='core.pipelinerun')),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pipeline_stages', to='core.application')),
            ],
            options={'ordering': ['sort_rank'], 'unique_together': {('pipeline', 'application')}},
        ),
    ]
