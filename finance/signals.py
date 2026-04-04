from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import create_default_categories_for_user


@receiver(post_save, sender=User)
def create_starter_categories(sender, instance, created, **kwargs):
    if created:
        create_default_categories_for_user(instance)
