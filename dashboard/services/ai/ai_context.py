from dashboard.services.context_builders.sales_context import (
    build_sales_context
)

from dashboard.services.context_builders.inventory_context import (
    build_inventory_context
)

from dashboard.services.context_builders.supplier_context import (
    build_supplier_context
)

from dashboard.services.context_builders.system_context import (
    build_system_context
)

from dashboard.services.context_builders.ghana_business_context import (
    build_ghana_business_context
)


def build_business_context(business, user):

    builders = [

        build_system_context(
            business,
            user
        ),

        build_ghana_business_context(),

        build_sales_context(
            business
        ),

        build_inventory_context(
            business
        ),

        build_supplier_context(
            business
        )

    ]

    return "\n".join(builders)