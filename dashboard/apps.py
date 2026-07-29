from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'


class BusinessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "business"

    def ready(self):
        from . import signals  # noqa: F401