from django.db import models

# Create your models here.

# dashboard/models.py

from django.db import models
from django.contrib.auth.models import User
from business.models import Business


# dashboard/models.py

from django.db import models
from django.contrib.auth.models import User

from business.models import Business


class AIChatHistory(models.Model):

    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user_message = models.TextField()
    ai_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ['-created_at']

    def __str__(self):

        return (
            f"{self.user.username} - "
            f"{self.business.name}"
        )


# dashboard/models.py

class AIMemory(models.Model):

    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE
    )

    memory = models.TextField(
        blank=True,
        null=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.business.name


class BusinessAlert(models.Model):

    ALERT_TYPES = (
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
        ('info', 'Info'),
    )

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE
    )

    title = models.CharField(max_length=255)

    message = models.TextField()

    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        default='info'
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class ForecastLog(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)

    forecast_type = models.CharField(max_length=100)

    prediction = models.TextField()

    confidence = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.forecast_type


class AIRecommendation(models.Model):

    RECOMMENDATION_TYPES = (
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
        ('primary', 'Primary'),
    )

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    title = models.CharField(max_length=255)

    message = models.TextField()

    icon = models.CharField(
        max_length=100,
        default='fas fa-lightbulb'
    )

    type = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_TYPES,
        default='primary'
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

