from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from InsightApp.services.analyzer import compute_kpis, revenue_by, revenue_over_time
from InsightApp.services.csv_loader import detect_schema, load_csv

SAMPLE = b"""date,product,quantity,price,city
2026-01-05,Laptop,2,450000,Douala
2026-01-06,Printer,1,120000,Yaounde
2026-02-05,Laptop,1,450000,Douala
"""


def test_load_and_detect_schema():
    df = load_csv(SAMPLE)
    schema = detect_schema(df)
    assert schema["date"] == "date"
    assert schema["amount"] == "price"
    assert schema["product"] == "product"
    assert schema["city"] == "city"


def test_compute_kpis():
    df = load_csv(SAMPLE)
    kpis = compute_kpis(df, detect_schema(df))
    assert kpis["Rows"] == 3
    assert kpis["Total revenue"] == 1_020_000
    assert kpis["Top product"] == "Laptop"


def test_revenue_by_city():
    df = load_csv(SAMPLE)
    schema = detect_schema(df)
    result = revenue_by(df, schema, "city")
    assert not result.empty
    assert result.iloc[0]["city"] == "Douala"


def test_revenue_over_time():
    df = load_csv(SAMPLE)
    schema = detect_schema(df)
    result = revenue_over_time(df, schema)
    assert len(result) == 2


@pytest.mark.django_db
def test_index_view(client):
    response = client.get(reverse("insight:index"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_analyze_view(client):
    upload = SimpleUploadedFile("sample.csv", SAMPLE, content_type="text/csv")
    response = client.post(reverse("insight:analyze"), {"file": upload})
    assert response.status_code == 200
    assert b"Dashboard" in response.content