from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import PurchaseItem

@receiver(post_save, sender=PurchaseItem)
@receiver(post_delete, sender=PurchaseItem)
def update_purchase_total(sender, instance, **kwargs):

    purchase = instance.purchase

    total = sum(item.total_cost for item in purchase.items.all())

    purchase.total_cost = total
    purchase.save()