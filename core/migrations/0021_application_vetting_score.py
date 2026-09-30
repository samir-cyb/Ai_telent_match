from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_pipeline_run'),
    ]

    operations = [
        migrations.AddField(
            model_name='application',
            name='vetting_score',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
