import uuid

from django.db import models


class Analysis(models.Model):
    # Identifiant public (URL-safe) pour l'export PDF
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    filename = models.CharField(max_length=255)
    rows = models.IntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )

    # CSV brut (pour régénérer le PDF plus tard)
    csv_data = models.BinaryField(null=True, blank=True)

    # Schéma détecté (JSON : {date, amount, quantity, product, city, revenue})
    schema = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.rows} lignes)"