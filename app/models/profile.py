import secrets
import time
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver
from app.models import Task
from django.db.models import Sum
from django.core.cache import cache
from webodm import settings


API_KEY_MASK_CHARACTER = "\u2022"


def generate_api_key():
    return secrets.token_hex(32)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    quota = models.FloatField(default=-1, blank=True, help_text=_("Maximum disk quota in megabytes"), verbose_name=_("Quota"))
    api_key = models.CharField(max_length=64, unique=True, default=generate_api_key, editable=False, verbose_name=_("API key"))

    def has_quota(self):
        return self.quota != -1

    def used_quota(self):
        q = Task.objects.filter(project__owner=self.user).aggregate(total=Sum('size'))['total']
        if q is None:
            q = 0
        return q

    def has_exceeded_quota(self):
        if not self.has_quota():
            return False

        q = self.used_quota()
        return q > self.quota

    def used_quota_cached(self):
        k = f'used_quota_{self.user.id}'
        cached = cache.get(k)
        if cached is not None:
            return cached

        v = self.used_quota()
        cache.set(k, v, 1800) # 30 minutes
        return v

    def has_exceeded_quota_cached(self):
        if not self.has_quota():
            return False

        q = self.used_quota_cached()
        return q > self.quota

    def clear_used_quota_cache(self):
        cache.delete(f'used_quota_{self.user.id}')

    def get_quota_deadline(self):
        return cache.get(f'quota_deadline_{self.user.id}')

    def set_quota_deadline(self, hours):
        k = f'quota_deadline_{self.user.id}'
        seconds = (hours * 60 * 60)
        v = time.time() + seconds
        cache.set(k, v, int(max(seconds * 10, settings.QUOTA_EXCEEDED_GRACE_PERIOD * 60 * 60)))
        return v

    def clear_quota_deadline(self):
        cache.delete(f'quota_deadline_{self.user.id}')

    def masked_api_key(self, visible_chars=8):
        if not self.api_key:
            return ""

        visible_chars = max(int(visible_chars), 0)
        suffix = self.api_key[-visible_chars:] if visible_chars else ""
        hidden_length = max(len(self.api_key) - len(suffix), 0)
        return f"{API_KEY_MASK_CHARACTER * hidden_length}{suffix}"

    def regenerate_api_key(self):
        self.api_key = generate_api_key()
        self.save(update_fields=['api_key'])
        return self.api_key


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
