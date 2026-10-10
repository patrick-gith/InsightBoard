"""
Lecture robuste d'un CSV uploadé + détection automatique de la devise.
"""
from __future__ import annotations

import csv
from io import BytesIO

import pandas as pd


# ==========================================================
# Mots-clés de détection (FR + EN)
# ==========================================================

DATE_HINTS = ("date", "created", "day", "jour", "mois", "month", "annee", "year")

# ⚠️ Deux groupes pour la colonne "montant" : on préfère un TOTAL
#    à un prix unitaire, sinon on multiplierait par erreur.
AMOUNT_HINTS_PRIMARY = (          # → colonnes déjà agrégées / totales
    "total", "revenue", "montant", "chiffre", "valeur", "amount", "subtotal", "ca",
)
AMOUNT_HINTS_SECONDARY = (        # → prix unitaires (à multiplier par qty)
    "price", "prix", "unit_price", "unit", "rate", "tarif",
)

QTY_HINTS = ("quantity", "qty", "qte", "quantite", "nb", "count", "nombre")
PRODUCT_HINTS = ("product", "item", "sku", "produit", "article", "designation", "libelle")
CITY_HINTS = ("city", "ville", "region", "country", "pays", "zone", "localisation")
CURRENCY_HINTS = ("currency", "devise", "monnaie", "cur", "ccy")

# Indices permettant de savoir si une colonne "montant" est un prix unitaire.
UNIT_PRICE_HINTS = ("price", "prix", "unit", "rate", "tarif", "pu")


_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")
_NA_VALUES = ["", "NA", "N/A", "na", "n/a", "null", "NULL", "-", "—"]

REVENUE_COL = "_revenue"


# ==========================================================
# Table de correspondance des devises (symbole ↔ code)
# ==========================================================

CURRENCY_MAP = {
    "€":        ("EUR", "€"),
    "eur":      ("EUR", "€"),
    "euro":     ("EUR", "€"),
    "euros":    ("EUR", "€"),
    "$":        ("USD", "$"),
    "usd":      ("USD", "$"),
    "dollar":   ("USD", "$"),
    "dollars":  ("USD", "$"),
    "£":        ("GBP", "£"),
    "gbp":      ("GBP", "£"),
    "pound":    ("GBP", "£"),
    "fcfa":     ("XAF", "FCFA"),
    "xaf":      ("XAF", "FCFA"),
    "cfa":      ("XAF", "FCFA"),
    "mad":      ("MAD", "MAD"),
    "dirham":   ("MAD", "MAD"),
    "dh":       ("MAD", "MAD"),
    "chf":      ("CHF", "CHF"),
    "fr":       ("CHF", "CHF"),
    "jpy":      ("JPY", "¥"),
    "yen":      ("JPY", "¥"),
    "¥":        ("JPY", "¥"),
    "cad":      ("CAD", "C$"),
    "aud":      ("AUD", "A$"),
    "naira":    ("NGN", "₦"),
    "₦":        ("NGN", "₦"),
    "rand":     ("ZAR", "R"),
    "zar":      ("ZAR", "R"),
    "inr":      ("INR", "₹"),
    "₹":        ("INR", "₹"),
    "cny":      ("CNY", "¥"),
    "rmb":      ("CNY", "¥"),
    "brl":      ("BRL", "R$"),
    "real":     ("BRL", "R$"),
}

DEFAULT_CURRENCY = ("USD", "$")


# ==========================================================
# LECTURE
# ==========================================================

def _sniff_separator(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _read_with_encoding(content: bytes, encoding: str) -> pd.DataFrame:
    text_sample = content[:4096].decode(encoding, errors="replace")
    sep = _sniff_separator(text_sample)
    return pd.read_csv(
        BytesIO(content),
        encoding=encoding,
        sep=sep,
        na_values=_NA_VALUES,
        keep_default_na=True,
        skip_blank_lines=True,
    )


def load_csv(content: bytes) -> pd.DataFrame:
    if not content or not content.strip():
        raise ValueError("Fichier vide.")

    df: pd.DataFrame | None = None
    last_error: Exception | None = None

    for encoding in _ENCODINGS:
        try:
            df = _read_with_encoding(content, encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except pd.errors.EmptyDataError as exc:
            raise ValueError("Le fichier ne contient aucune donnée lisible.") from exc
        except Exception as exc:
            last_error = exc
            continue

    if df is None:
        raise ValueError(
            f"Impossible de lire le CSV (encodages testés : {', '.join(_ENCODINGS)}). "
            f"Dernière erreur : {last_error}"
        )

    if df.empty or df.shape[1] == 0:
        raise ValueError("Le fichier ne contient aucune colonne exploitable.")

    # Normalisation des noms de colonnes
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]

    # Déduplication des colonnes homonymes
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    df.columns = new_cols

    df = df.dropna(how="all").reset_index(drop=True)

    # Nettoyage des chaînes
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = (
            df[col].astype(str).str.strip()
            .replace({"nan": None, "None": None})
        )

    return df


# ==========================================================
# DÉTECTION DU SCHÉMA
# ==========================================================

def _find(columns: list[str], hints: tuple[str, ...]) -> str | None:
    """
    Cherche la première colonne correspondant à l'un des indices.

    Priorité (pour éviter les faux positifs type « ca » dans « cable ») :
        1. Nom exact             : col == hint
        2. Mot entier            : hint ∈ col.split("_")
        3. Sous-chaîne (legacy)  : hint in col
    """
    # 1. Match exact
    for col in columns:
        if col in hints:
            return col

    # 2. Match mot entier
    for col in columns:
        parts = set(col.split("_"))
        for hint in hints:
            if hint in parts:
                return col

    # 3. Fallback sous-chaîne (comportement historique)
    for col in columns:
        for hint in hints:
            if hint in col:
                return col

    return None


def _find_priority(columns: list[str], *hint_groups: tuple[str, ...]) -> str | None:
    """Essaie chaque groupe d'indices dans l'ordre, retourne le 1er match."""
    for hints in hint_groups:
        result = _find(columns, hints)
        if result:
            return result
    return None


def detect_schema(df: pd.DataFrame) -> dict:
    cols = df.columns.tolist()
    return {
        "date":         _find(cols, DATE_HINTS),
        # ⬇️ Priorité : TOTAL avant PRIX UNITAIRE
        "amount":       _find_priority(
                            cols,
                            AMOUNT_HINTS_PRIMARY,
                            AMOUNT_HINTS_SECONDARY,
                        ),
        "quantity":     _find(cols, QTY_HINTS),
        "product":      _find(cols, PRODUCT_HINTS),
        "city":         _find(cols, CITY_HINTS),
        "currency_col": _find(cols, CURRENCY_HINTS),
        "revenue":      REVENUE_COL if REVENUE_COL in cols else None,
        "all":          cols,
    }


# ==========================================================
# DÉTECTION DE LA DEVISE
# ==========================================================

def detect_currency(df: pd.DataFrame, schema: dict) -> dict:
    """
    Détecte la devise du fichier.

    Stratégie :
        1. Colonne 'currency' / 'devise' → 1re valeur non nulle
        2. Symbole monétaire dans les en-têtes de colonnes
        3. Fallback sur DEFAULT_CURRENCY ($)

    Retourne :
        {"code": ..., "symbol": ..., "source": "column"|"header"|"default", "raw": ...}
    """
    # --- 1. Colonne dédiée ---
    cur_col = schema.get("currency_col")
    if cur_col and cur_col in df.columns:
        values = df[cur_col].dropna().astype(str).unique()
        if len(values) > 0:
            raw = values[0].strip()
            code, symbol = _lookup_currency(raw)
            if code:
                return {"code": code, "symbol": symbol, "source": "column", "raw": raw}

    # --- 2. Symbole dans les noms de colonnes ---
    for col in df.columns:
        for token, (code, symbol) in CURRENCY_MAP.items():
            if token in col:
                return {"code": code, "symbol": symbol, "source": "header", "raw": token}

    # --- 3. Fallback ---
    return {
        "code": DEFAULT_CURRENCY[0],
        "symbol": DEFAULT_CURRENCY[1],
        "source": "default",
        "raw": None,
    }


def _lookup_currency(raw: str) -> tuple[str | None, str | None]:
    """Cherche une devise dans la table (insensible à la casse, partielle)."""
    if not raw:
        return None, None
    key = raw.strip().lower()
    if key in CURRENCY_MAP:
        return CURRENCY_MAP[key]
    for token, val in CURRENCY_MAP.items():
        if token in key:
            return val
    return None, None


# ==========================================================
# ENRICHISSEMENT
# ==========================================================

def _is_unit_price(col_name: str) -> bool:
    """
    True si la colonne ressemble à un PRIX UNITAIRE
    (donc à multiplier par la quantité pour obtenir le CA).
    """
    if not col_name:
        return False
    parts = set(col_name.split("_"))
    for hint in UNIT_PRICE_HINTS:
        if hint in parts or hint in col_name:
            return True
    return False


def enrich_revenue(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """
    Calcule '_revenue' = CA de chaque ligne.

    Règle :
        - Si la colonne 'amount' est un prix unitaire ET qu'une quantité existe
          → `amount × quantity`
        - Sinon (colonne déjà totalisée, ou pas de quantité)
          → on prend la valeur telle quelle
    """
    if REVENUE_COL in df.columns:
        return df

    amt = schema.get("amount")
    if not amt or amt not in df.columns:
        return df

    df = df.copy()
    df[amt] = pd.to_numeric(df[amt], errors="coerce")

    qty = schema.get("quantity")
    multiply = _is_unit_price(amt) and qty and qty in df.columns

    if multiply:
        df[qty] = pd.to_numeric(df[qty], errors="coerce")
        df[REVENUE_COL] = (df[amt] * df[qty]).fillna(df[amt])
    else:
        df[REVENUE_COL] = df[amt]

    return df