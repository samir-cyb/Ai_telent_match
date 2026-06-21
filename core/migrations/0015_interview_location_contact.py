from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_aiinterview'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledinterview',
            name='location',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='scheduledinterview',
            name='contact_person',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='scheduledinterview',
            name='meeting_type',
            field=models.CharField(default='in_person', max_length=20),
        ),
    ]
