from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Superusers always get admin role.
        # Otherwise, first ever user gets admin, everyone else gets readonly.
        if instance.is_superuser:
            role = 'admin'
        else:
            role = 'admin' if User.objects.count() == 1 else 'readonly'
        UserProfile.objects.get_or_create(user=instance, defaults={'role': role})
    else:
        # If an existing user is promoted to superuser, ensure they have admin role.
        profile = getattr(instance, 'profile', None)
        if instance.is_superuser and profile and profile.role != 'admin':
            profile.role = 'admin'
            profile.save()
