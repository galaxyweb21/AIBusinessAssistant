from inventory.models import Inventory


def build_inventory_context(business):

    inventory = (
        Inventory.objects
        .filter(business=business)
        .order_by("product_name")
    )

    LOW_STOCK_THRESHOLD = 5

    low_stock_items = inventory.filter(
        stock_quantity__lte=LOW_STOCK_THRESHOLD
    )

    total_products = inventory.count()

    product_names = []
    low_stock = []
    detailed_products = []

    for item in inventory:

        product_names.append(item.product_name)

        if item.stock_quantity <= LOW_STOCK_THRESHOLD:
            low_stock.append(
                f"{item.product_name} ({item.stock_quantity} left)"
            )

        detailed_products.append(
            (
                f"ID={item.id} | "
                f"NAME={item.product_name} | "
                f"STOCK={item.stock_quantity} | "
                f"PRICE={item.selling_price} | "
                f"BARCODE={item.barcode or 'N/A'}"
            )
        )

    return f"""
================ INVENTORY DATABASE ================

SYSTEM INSTRUCTION:

This is the LIVE inventory database.

When answering inventory questions:

- Use ONLY products listed in PRODUCT NAMES and PRODUCT DETAILS.
- Never invent products.
- Never use products from memory.
- Never use products from previous conversations.
- Never assume product names.
- If a product is not listed here, say:
  "That product does not exist in the current inventory."

-----------------------------------------------------

TOTAL PRODUCTS:
{total_products}

PRODUCT NAMES:
{", ".join(product_names) if product_names else "NO PRODUCTS FOUND"}

-----------------------------------------------------

LOW STOCK THRESHOLD:
{LOW_STOCK_THRESHOLD}

LOW STOCK PRODUCTS:
{", ".join(low_stock) if low_stock else "NONE"}

-----------------------------------------------------

PRODUCT DETAILS:

{chr(10).join(detailed_products)}

-----------------------------------------------------

EXAMPLE CORRECT RESPONSE:

Question:
"What products do I have?"

Answer:
"Your inventory contains:
{', '.join(product_names[:20])}"

====================================================
"""