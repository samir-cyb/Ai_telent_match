from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_aiinterview_expires_at_gemini_analysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiinterview',
            name='cheating_log',
            field=models.JSONField(
                null=True, blank=True,
                help_text='Anti-cheat violation log: tab_switches, fullscreen_exits, copy_pastes, auto_submitted'
            ),
        ),
    ]
