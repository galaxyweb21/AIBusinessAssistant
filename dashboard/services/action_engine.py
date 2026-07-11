def generate_actions(question, response):

    q = question.lower()

    actions = []

    if "low stock" in q:
        actions = [
            {
                "label": "View Low Stock",
                "url": "/inventory/?filter=low"
            },
            {
                "label": "Create Purchase Order",
                "url": "/purchases/create/"
            }
        ]

    elif "supplier" in q:
        actions = [
            {
                "label": "View Suppliers",
                "url": "/suppliers/"
            }
        ]

    elif "profit" in q:
        actions = [
            {
                "label": "Profit Report",
                "url": "/reports/profit/"
            }
        ]

    return actions