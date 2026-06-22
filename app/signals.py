from django.db.models import signals
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from app.plugins.signals import task_completed
import logging

logger = logging.getLogger('app.logger')

@receiver(signals.post_save, sender=User, dispatch_uid="user_check_default_group")
def check_default_group(sender, instance, created, **kwargs):
    if created:
        try:
            default_group = Group.objects.get(name="Default")
            instance.groups.add(default_group)
            instance.save()
            logger.info("Added {} to default group".format(instance.username))
        except:
            pass # Group "Default" is not available, probably loading fixtures at this moment...


@receiver(task_completed, dispatch_uid="airtwin_task_completed")
def handle_airtwin_task_completed(sender, task_id, **kwargs):
    from app.services.airtwin import schedule_task_completed_webhook
    from worker.tasks import deliver_airtwin_webhook

    schedule_task_completed_webhook(task_id, enqueue=deliver_airtwin_webhook.delay)
