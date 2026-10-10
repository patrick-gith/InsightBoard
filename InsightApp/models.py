import uuid

from django.db import models


class Analysis(models.Model):
    STATUS_CHOICES = [
        ("pending",    "En attente"),
        ("processing", "En cours"),
        ("completed",  "Terminée"),
        ("failed",     "Échouée"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    filename = models.CharField(max_length=255)
    rows = models.IntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )

    # Mode local  : csv_data rempli, dashboard_data vide
    # Mode github : csv_data NULL,   dashboard_data rempli par le webhook
    csv_data       = models.BinaryField(null=True, blank=True)
    dashboard_data = models.JSONField(default=dict, blank=True)

    schema = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="completed"
    )
    pdf_artifact = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.rows} lignes)"