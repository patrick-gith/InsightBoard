"""
Construction des données du dashboard (KPI, graphiques, stats).

Partagé entre :
    - InsightApp.views (mode local + affichage dashboard)
    - InsightApp.management.commands.run_analysis (GitHub Actions)

Ce module NE dépend PAS de la couche modèle : il transforme uniquement
un DataFrame + un schéma en structures prêtes à être rendues.
"""
from __future__ import annotations

import logging

from django.utils.translation import gettext as _

from .analyzer import compute_kpis, revenue_by, revenue_over_time
from .charts import (
    build_bar, build_line, build_donut, fig_to_data_uri, fig_to_html,
)
from .csv_loader import detect_currency, detect_schema, enrich_revenue, load_csv
from .formatting import format_amount, format_int

logger = logging.getLogger(__name__)


# ==========================================================
# LIBELLÉS + META
# ==========================================================
KPI_LABELS = {
    "Rows":           _("Lignes"),
    "Total revenue":  _("Chiffre d'affaires"),
    "Average order":  _("Panier moyen"),
    "Total quantity": _("Quantité totale"),
    "Top product":    _("Produit le plus vendu"),
    "Top city":       _("Ville principale"),
}

KPI_META = {
    "Rows":           ("fa-list",          "lignes", "int"),
    "Total revenue":  ("fa-coins",         "",       "amount"),
    "Average order":  ("fa-cart-shopping", "",       "amount"),
    "Total quantity": ("fa-boxes-stacked", "unités", "int"),
    "Top product":    ("fa-crown",         "",       "raw"),
    "Top city":       ("fa-location-dot",  "",       "raw"),
}

DEFAULT_META = ("fa-chart-simple", "", "raw")


# ==========================================================
# HELPERS
# ==========================================================
def revenue_col(schema: dict) -> str | None:
    return schema.get("revenue") or schema.get("amount")


def prepare_dataframe(content: bytes):
    """Charge + enrichit un CSV et retourne (df, schema)."""
    df = load_csv(content)
    if df.empty:
        return df, {}
    schema = detect_schema(df)
    df = enrich_revenue(df, schema)
    schema = detect_schema(df)
    return df, schema


# ==========================================================
# KPI
# ==========================================================
def build_kpi_entry(en_key: str, value, currency: dict) -> dict:
    label = str(KPI_LABELS.get(en_key, en_key))
    icon, unit_hint, kind = KPI_META.get(en_key, DEFAULT_META)

    if kind == "amount":
        value_display = format_amount(value, currency["symbol"], mode="full")
        compact = format_amount(value, currency["symbol"], mode="short")
        value_multiple = "" if compact == value_display else compact
        unit = ""
    elif kind == "int":
        value_display = format_int(value)
        value_multiple = ""
        unit = unit_hint
    else:
        value_display = str(value)
        value_multiple = ""
        unit = ""

    return {
        "key":            en_key,
        "label":          label,
        "raw":            value,
        "value":          value_display,
        "value_display":  value_display,
        "value_multiple": value_multiple,
        "unit":           unit,
        "icon":           icon,
        "kind":           kind,
    }


# ==========================================================
# GRAPHIQUES
# ==========================================================
def build_chart_specs(df, schema, currency_symbol: str, *, for_pdf=False):
    rev_col = revenue_col(schema)
    charts: list[dict] = []

    def add(title, description, builder, data, *args, **kwargs):
        if data.empty:
            return
        fig = builder(data, *args, **kwargs)
        if for_pdf:
            try:
                charts.append({
                    "title": title,
                    "description": description,
                    "image": fig_to_data_uri(fig, width=900, scale=1.8),
                })
            except Exception as exc:
                logger.warning("Kaleido échec : %s", exc)
        else:
            charts.append({
                "title": title,
                "description": description,
                "html": fig_to_html(fig),
            })

    if schema.get("city") and rev_col:
        d = revenue_by(df, schema, schema["city"]).head(15)
        add(str(_("Chiffre d'affaires par ville")),
            str(_("Répartition du chiffre d'affaires par ville. "
                  "Les 15 villes les plus contributrices sont affichées, "
                  "triées par ordre décroissant.")),
            build_bar, d, schema["city"], rev_col,
            str(_("Chiffre d'affaires par ville")),
            currency_symbol=currency_symbol)

    if schema.get("product") and rev_col:
        d = revenue_by(df, schema, schema["product"]).head(10)
        add(str(_("Top 10 produits")),
            str(_("Classement des 10 produits générant le chiffre d'affaires le plus élevé.")),
            build_bar, d, schema["product"], rev_col,
            str(_("Top 10 produits")),
            currency_symbol=currency_symbol)

    if schema.get("product") and rev_col:
        d = revenue_by(df, schema, schema["product"])
        add(str(_("Répartition du CA par produit")),
            str(_("Poids de chaque produit dans le chiffre d'affaires total. "
                  "Les produits les moins significatifs sont regroupés sous « Autres ».")),
            build_donut, d, schema["product"], rev_col,
            str(_("Répartition du CA par produit")),
            currency_symbol=currency_symbol, top_n=6)

    if schema.get("date") and rev_col:
        d = revenue_over_time(df, schema)
        add(str(_("Évolution du chiffre d'affaires")),
            str(_("Évolution mensuelle du chiffre d'affaires. Chaque point "
                  "représente le total des transactions du mois correspondant.")),
            build_line, d, "period", rev_col,
            str(_("Évolution du chiffre d'affaires")),
            currency_symbol=currency_symbol)

    return charts


# ==========================================================
# STATS
# ==========================================================
def build_stats(df, schema, kpis, currency) -> dict:
    import pandas as pd

    stats: dict = {
        "period_start": None,
        "period_end": None,
        "nb_products": None,
        "nb_cities": None,
        "min_transaction": None,
        "max_transaction": None,
        "currency_symbol": currency["symbol"],
        "currency_source": currency["source"],
        "currency_raw": currency.get("raw"),
    }

    date_col = schema.get("date")
    if date_col and date_col in df.columns:
        try:
            dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if not dates.empty:
                stats["period_start"] = dates.min().strftime("%d/%m/%Y")
                stats["period_end"] = dates.max().strftime("%d/%m/%Y")
        except Exception:
            pass

    prod = schema.get("product")
    if prod and prod in df.columns:
        stats["nb_products"] = int(df[prod].nunique())

    city = schema.get("city")
    if city and city in df.columns:
        stats["nb_cities"] = int(df[city].nunique())

    rev = revenue_col(schema)
    if rev and rev in df.columns:
        series = pd.to_numeric(df[rev], errors="coerce").dropna()
        if not series.empty:
            stats["min_transaction"] = format_amount(
                series.min(), currency["symbol"], mode="full"
            )
            stats["max_transaction"] = format_amount(
                series.max(), currency["symbol"], mode="full"
            )

    return stats


# ==========================================================
# PAYLOAD COMPLET (utilisé par le dashboard et par run_analysis)
# ==========================================================
def build_dashboard_payload(df, schema, currency, *, filename: str) -> dict:
    """
    Construit le payload complet du dashboard :
    KPI formatés + graphiques HTML + stats + colonnes + devise.
    """
    kpis_raw = compute_kpis(df, schema)
    kpis_display = [build_kpi_entry(k, v, currency) for k, v in kpis_raw.items()]
    stats = build_stats(df, schema, kpis_raw, currency)
    charts_html = build_chart_specs(df, schema, currency["symbol"], for_pdf=False)

    return {
        "filename":      filename,
        "kpis":          kpis_display,
        "kpis_count":    len(kpis_display),
        "charts":        charts_html,
        "columns":       schema["all"],
        "schema":        schema,
        "currency":      currency,
        "rows":          len(df),
        "stats":         stats,
        "total_revenue": kpis_raw.get("Total revenue"),
    }