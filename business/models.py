import os
from datetime import datetime

from django.db import models
from django.contrib.auth.models import User


def get_file_path(request, filename):

    original_filename = filename

    nowTime = datetime.now().strftime('%y%m%d%H%M%S')

    filename = f"{nowTime}_{original_filename}"

    return os.path.join('uploads/', filename)


class Business(models.Model):

    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='business/', blank=True, null=True, default='business/No-Picture.png')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name