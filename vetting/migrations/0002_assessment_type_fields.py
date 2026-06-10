from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vetting', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vettingchallenge',
            name='assessment_type',
            field=models.CharField(
                choices=[('coding', 'Coding Challenge'), ('mcq_written', 'MCQ + Written')],
                default='coding',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='vettingchallenge',
            name='department_category',
            field=models.CharField(blank=True, default='any', max_length=20),
        ),
        migrations.AddField(
            model_name='vettingchallenge',
            name='topic_focus',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='vettingchallenge',
            name='mcq_questions',
            field=models.JSONField(default=list),
        ),
    ]
