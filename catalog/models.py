
from business.models import Business
import uuid
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, blank=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    icon = models.CharField(max_length=50, blank=True, help_text="FontAwesome icon e.g. fas fa-box")
    color = models.CharField(max_length=20, default="#4f46e5")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        unique_together = ("business", "name")

    def save(self, *args, **kwargs):

        if not self.slug:
            self.slug = slugify(self.name)

        if not self.code:
            self.code = "CAT-" + uuid.uuid4().hex[:6].upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def total_products(self):
        return self.products.count()