import os
from django.db import models
# from django.contrib.auth.models import AbstractUser

from django.contrib.auth.models import User
from datetime import date, datetime
from business.models import *
from business.views import *
from django.db.models.signals import post_save
from django.dispatch import receiver
import secrets
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.fields import GenericRelation


def get_file_path(request, filename):
    original_filename = filename
    nowTime = datetime.datetime.now().strftime('%y%m%d%H:%M:%S')
    filename = "%s%s" % (nowTime, original_filename)
    return os.path.join('uploads/', filename)


class AuditLog(models.Model):

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.action}"


class StaffProfile(models.Model):
    role = (("Cashier", "Cashier"), ("Sales", "Sales"), ("Admin", "Admin"),
              ("Branch Manager", "Branch Manager"))
    staff = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    contact = models.CharField(max_length=20, blank=True, null=True)
    role_type = models.CharField(max_length=50, blank=True, null=True, choices=role)
    is_active = models.BooleanField(default=True)
    auditlog_set = GenericRelation(
        AuditLog
    )

    def __str__(self):
        return self.staff.first_name + ' ' + self.staff.last_name

    # def save(self, *args, **kwargs):
    #     if not self.pin_code:
    #         self.pin_code = str(secrets.randbelow(9000) + 1000)
    #     super().save(*args, **kwargs)