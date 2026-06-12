from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_linkedin_and_advanced'),
    ]

    operations = [
        # Make application nullable (manual edits have no application)
        migrations.AlterField(
            model_name='aifeedbacklog',
            name='application',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ai_feedback',
                to='core.application',
            ),
        ),
        # New fields
        migrations.AddField(
            model_name='aifeedbacklog',
            name='trigger',
            field=models.CharField(
                choices=[('hire', 'Candidate Hired'),
                         ('reject', 'Shortlisted Candidate Rejected'),
                         ('manual', 'Company Manually Edited Weights')],
                default='hire', max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='aifeedbacklog',
            name='reward',
            field=models.FloatField(default=1.0),
        ),
        migrations.AddField(
            model_name='aifeedbacklog',
            name='candidate_features',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='aifeedbacklog',
            name='weight_delta',
            field=models.JSONField(default=dict),
        ),
    ]
