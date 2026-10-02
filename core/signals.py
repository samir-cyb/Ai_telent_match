from django.db.models import F
from django.db.models.functions import Greatest
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Application, Job


@receiver(post_save, sender=Application)
def application_created(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        Job.objects.filter(pk=instance.job_id).update(total_applicants=F('total_applicants') + 1)


@receiver(post_delete, sender=Application)
def application_deleted(sender, instance, **kwargs):
    Job.objects.filter(pk=instance.job_id).update(total_applicants=Greatest(F('total_applicants') - 1, 0))
