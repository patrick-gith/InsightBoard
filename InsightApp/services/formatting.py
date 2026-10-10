"""
Formatage des nombres et devises pour l'affichage et le PDF.

Expose :
    - format_amount(value, currency, mode="auto")   → "1,25 M $" ou "3 125 000 $"
    - format_number(value)                          → "3 125 000"
    - format_int(value)                             → "1 284"
    - format_percent(value)                         → "+5,6 %"
"""
from __future__ import annotations


def format_int(value) -> str:
    """Formate un entier avec séparateur d'espace : 1284 → '1 284'."""
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def format_number(value, *, decimals: int = 0) -> str:
    """Formate un nombre à virgule : 1234.567 → '1 234,57'."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if decimals == 0:
        s = f"{num:,.0f}"
    else:
        s = f"{num:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",")


from decimal import Decimal, ROUND_HALF_UP


def _round_half_up(num: float, decimals: int) -> str:
    """Arrondi commercial (0.5 → supérieur), pas l'arrondi bancaire Python."""
    q = Decimal(1).scaleb(-decimals)               # 10^-decimals
    d = Decimal(str(num)).quantize(q, rounding=ROUND_HALF_UP)
    return f"{d:,.{decimals}f}".replace(",", " ").replace(".", ",")


def format_amount(value, currency_symbol: str = "$", *, mode: str = "auto") -> str:
    """
    Formate un montant avec multiples appropriés.

    Modes :
        - "auto"  : bascule automatique (3 125 000 $ → "3,13 M $")
        - "full"  : EXACT — entier sans décimale, sinon 2 décimales
                    (446428.5714… → "446 428,57 $")
        - "short" : toujours en compact ("3,13 M $")
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    symbol = currency_symbol or ""

    # ----- Mode full : valeur exacte, sans troncature -----
    if mode == "full":
        if num.is_integer():
            return f"{format_number(num, decimals=0)} {symbol}".strip()
        return f"{_round_half_up(num, 2)} {symbol}".strip()

    abs_num = abs(num)

    # ----- Choisir le multiple (auto / short) -----
    if abs_num >= 1_000_000_000:
        scaled, suffix, decimals = num / 1_000_000_000, "G", 2
    elif abs_num >= 1_000_000:
        scaled, suffix, decimals = num / 1_000_000, "M", 2
    elif abs_num >= 1_000 and mode == "short":
        scaled, suffix, decimals = num / 1_000, "k", 1
    else:
        if num.is_integer():
            return f"{format_number(num, decimals=0)} {symbol}".strip()
        return f"{_round_half_up(num, 2)} {symbol}".strip()

    return f"{_round_half_up(scaled, decimals)} {suffix} {symbol}".strip()


def format_percent(value, *, decimals: int = 1) -> str:
    """Formate un pourcentage : -5.6 → '-5,6 %'."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{num:+.{decimals}f}".replace(".", ",")
    return f"{s} %"


def format_multiple(value, unit: str = "") -> str:
    """
    Formate un entier en multiple pour les axes/étiquettes :
        1200 → "1,2k"
        1_500_000 → "1,5M"
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    abs_num = abs(num)
    if abs_num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}".replace(".", ",") + "G" + (f" {unit}" if unit else "")
    if abs_num >= 1_000_000:
        return f"{num / 1_000_000:.1f}".replace(".", ",") + "M" + (f" {unit}" if unit else "")
    if abs_num >= 1_000:
        return f"{num / 1_000:.1f}".replace(".", ",") + "k" + (f" {unit}" if unit else "")
    return f"{num:.0f}" + (f" {unit}" if unit else "")