"""
Analyse de fichiers CSV.

Les clés de KPI sont en ANGLAIS pour rester stables côté service ;
la traduction se fait dans views.py via kpi_labels.

Toutes les agrégations de chiffre d'affaires utilisent la colonne
'_revenue' (quantité × prix unitaire) si elle existe, sinon
retombent sur 'amount'.
"""
from __future__ import annotations

import pandas as pd


# ==========================================================
# HELPER
# ==========================================================

def _revenue_col(schema: dict) -> str | None:
    """Colonne à utiliser pour les agrégats de CA."""
    return schema.get("revenue") or schema.get("amount")


# ==========================================================
# KPIs
# ==========================================================

def compute_kpis(df: pd.DataFrame, schema: dict) -> dict:
    """
    Retourne un dict dont les clés correspondent EXACTEMENT
    à celles mappées dans views.py :
        "Rows", "Total revenue", "Average order",
        "Total quantity", "Top product", "Top city"
    """
    kpis: dict = {"Rows": int(len(df))}

    rev = _revenue_col(schema)
    if rev and rev in df.columns:
        series = pd.to_numeric(df[rev], errors="coerce")
        if series.notna().any():
            kpis["Total revenue"] = float(series.sum(skipna=True))
            kpis["Average order"] = float(series.mean(skipna=True))

    qty = schema.get("quantity")
    if qty and qty in df.columns:
        series_q = pd.to_numeric(df[qty], errors="coerce")
        if series_q.notna().any():
            kpis["Total quantity"] = int(series_q.sum(skipna=True))

    prod = schema.get("product")
    if prod and prod in df.columns:
        vc = df[prod].dropna().astype(str).value_counts()
        if not vc.empty:
            kpis["Top product"] = str(vc.idxmax())

    city = schema.get("city")
    if city and city in df.columns:
        vc = df[city].dropna().astype(str).value_counts()
        if not vc.empty:
            kpis["Top city"] = str(vc.idxmax())

    return kpis


# ==========================================================
# AGRÉGATIONS POUR GRAPHIQUES
# ==========================================================

def revenue_by(df: pd.DataFrame, schema: dict, group_col: str) -> pd.DataFrame:
    """
    Agrège le CA par une colonne catégorielle.

    Retourne [group_col, revenue_col] trié décroissant. La colonne
    de valeur porte le nom de la colonne utilisée ('_revenue' ou 'amount').
    """
    rev = _revenue_col(schema)
    if not rev or not group_col:
        return pd.DataFrame()
    if rev not in df.columns or group_col not in df.columns:
        return pd.DataFrame()

    tmp = df[[group_col, rev]].copy()
    tmp[rev] = pd.to_numeric(tmp[rev], errors="coerce")
    tmp = tmp.dropna(subset=[group_col, rev])

    if tmp.empty:
        return pd.DataFrame()

    return (
        tmp.groupby(group_col, as_index=False)[rev]
           .sum()
           .sort_values(rev, ascending=False)
    )


def revenue_over_time(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """
    Agrège le CA par mois.

    Retourne [period, revenue_col] trié chronologiquement.
    'period' est une chaîne 'YYYY-MM'.
    """
    date = schema.get("date")
    rev = _revenue_col(schema)
    if not date or not rev:
        return pd.DataFrame()
    if date not in df.columns or rev not in df.columns:
        return pd.DataFrame()

    tmp = df[[date, rev]].copy()
    tmp[date] = pd.to_datetime(tmp[date], errors="coerce")
    tmp[rev] = pd.to_numeric(tmp[rev], errors="coerce")
    tmp = tmp.dropna(subset=[date, rev])

    if tmp.empty:
        return pd.DataFrame()

    tmp["period"] = tmp[date].dt.to_period("M").astype(str)
    return (
        tmp.groupby("period", as_index=False)[rev]
           .sum()
           .sort_values("period")
    )