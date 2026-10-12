from django.conf import settings

if settings.USE_LOCAL_DB:
    from django.contrib import admin
    from .models import Analysis

    @admin.register(Analysis)
    class AnalysisAdmin(admin.ModelAdmin):
        list_display = ("uuid", "filename", "status", "rows", "created_at")
        list_filter  = ("status",)
        search_fields = ("filename", "uuid")
        readonly_fields = ("uuid", "created_at")