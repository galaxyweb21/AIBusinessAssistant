"""
Keeps the sidebar badge counts fresh by clearing the cached value the
instant something that affects them changes, instead of waiting out the
60s TTL in context_processors.py.

Wire this up in your app's apps.py:

    # business/apps.py
    from django.apps import AppConfig

    class BusinessConfig(AppConfig):
        default_auto_field = "django.db.models.BigAutoField"
        name = "business"

        def ready(self):
            from . import signals  # noqa: F401  (registers the receivers below)

(Django only connects signal receivers once the module they live in has
been imported somewhere — ready() is the standard place to do that.)
"""

from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from inventory.models import Inventory
from sales.models import Sale, Customer  # adjust "sales" to match this app's actual label

from .context_processors import cache_key_for


def _bust(business_id):
    if business_id:
        cache.delete(cache_key_for(business_id))


@receiver(post_save, sender=Inventory)
@receiver(post_delete, sender=Inventory)
def bust_on_inventory_change(sender, instance, **kwargs):
    _bust(instance.business_id)


@receiver(post_save, sender=Sale)
@receiver(post_delete, sender=Sale)
def bust_on_sale_change(sender, instance, **kwargs):
    _bust(instance.business_id)


@receiver(post_save, sender=Customer)
@receiver(post_delete, sender=Customer)
def bust_on_customer_change(sender, instance, **kwargs):
    _bust(instance.business_id)
