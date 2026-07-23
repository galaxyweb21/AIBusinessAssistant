from decimal import Decimal
from django.db import transaction

from .models import Inventory
from .models import InventoryMovement

@transaction.atomic
def restock_product(
    *,
    product,
    quantity,
    unit_cost,
    user,
    reference="",
    notes=""
):

    before = product.stock_quantity

    after = before + quantity

    product.stock_quantity = after

    product.cost_price = unit_cost

    product.save()

    InventoryMovement.objects.create(

        business=product.business,

        product=product,

        movement_type="RESTOCK",

        quantity=quantity,

        before_quantity=before,

        after_quantity=after,

        unit_cost=unit_cost,

        total_cost=Decimal(quantity) * unit_cost,

        reference=reference,

        notes=notes,

        created_by=user

    )

    return product


@transaction.atomic
def damage_product(
    *,
    product,
    quantity,
    user,
    notes=""
):

    before = product.stock_quantity

    after = max(before - quantity, 0)

    product.stock_quantity = after

    product.save()

    InventoryMovement.objects.create(

        business=product.business,

        product=product,

        movement_type="DAMAGE",

        quantity=quantity,

        before_quantity=before,

        after_quantity=after,

        unit_cost=product.cost_price,

        total_cost=Decimal(quantity) * product.cost_price,

        notes=notes,

        created_by=user

    )

    return product