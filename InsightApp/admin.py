from django.contrib import admin
from .models import Analysis


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("filename", "rows", "total_revenue", "created_at")
    list_filter = ("created_at",)
    search_fields = ("filename",)