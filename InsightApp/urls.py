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
]

