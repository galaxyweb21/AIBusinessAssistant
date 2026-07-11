from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from inventory.models import Supplier


def build_supplier_context(
        business
):

    suppliers = (

        Supplier.objects.filter(
            business=business
        )
        .annotate(

            total_purchase=

            Coalesce(
                Sum(
                    "purchase__total_cost"
                ),
                Decimal("0")
            )

        )

    )

    supplier_data=[]

    for supplier in suppliers:

        supplier_data.append(

            f"{supplier.name}: "
            f"GHS {supplier.total_purchase}"

        )

    top_supplier=(

        suppliers.order_by(
            "-total_purchase"
        ).first()

    )

    highest_supplier=(

        f"{top_supplier.name}"
        f" (GHS {top_supplier.total_purchase})"

        if top_supplier
        else "None"

    )

    return f"""

SUPPLIERS:

Highest Supplier:

{highest_supplier}

Supplier Summary:

{", ".join(supplier_data)}

"""