from django.http import JsonResponse
from django.urls import path

from . import views

app_name = "insight"


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", views.home, name="index"),
    path("analyze/", views.analyze, name="analyze"),
    path("export/<uuid:uuid>/pdf/", views.export_pdf, name="export_pdf"),
    path("health/", health, name="health"),
     
    path("dashboard/<uuid:uuid>/", views.dashboard, name="dashboard"),
    path("dashboard/<uuid:uuid>/waiting/", views.analysis_waiting, name="analysis_waiting"),
    path("dashboard/<uuid:uuid>/status/", views.analysis_status, name="analysis_status"),
    path("webhook/analysis/", views.analysis_webhook, name="analysis_webhook"),

    path("export/<uuid:uuid>/pdf/", views.export_pdf, name="export_pdf"),
    path("health/", health, name="health"),
]

