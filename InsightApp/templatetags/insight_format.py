"""
Filtres de formatage pour les templates.

Expose :
    - smart_format(value, unit)   → valeur lisible ("3 125 000 €" / "Paris")
    - exact_amount(value, unit)   → alias sémantique de smart_format
    - scale_amount(value, unit)   → multiple adapté (k / M / G) si |v| ≥ 1000, sinon ""
    - exact_int(value)            → entier avec séparateurs d'espace
    - exact_number(value, dec)    → nombre décimal localisé
"""
from django import template

from InsightApp.services.formatting import (
    format_amount,
    format_int,
    format_number,
)

register = template.Library()


@register.filter
def smart_format(value, unit=""):
    """
    Formate une valeur de façon lisible :
        - nombre       → montant exact avec séparateurs ("3 125 000 €")
        - chaîne       → tel quel ("Paris", "Coca-Cola")
        - None / ""    → "" (pas d'erreur d'affichage)
    """
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return format_amount(num, unit, mode="full")


@register.filter
def exact_amount(value, unit=""):
    """Alias sémantique de smart_format (force mode exact)."""
    return smart_format(value, unit)


@register.filter
def scale_amount(value, unit=""):
    """
    Retourne le multiple adapté (k / M / G) si |valeur| ≥ 1000, sinon "".
    Utilisé pour la version compacte sous la valeur exacte.

    Exemples (unit="€") :
        500        → ""
        1 250      → "1,3 k €"
        1 250 000  → "1,25 M €"
        2 500 M    → "2,50 G €"
        "Paris"    → ""
    """
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(num) < 1000:
        return ""
    return format_amount(num, unit, mode="short")


@register.filter
def exact_int(value):
    """Entier avec séparateur d'espace : 1284 → '1 284'."""
    return format_int(value)


@register.filter
def exact_number(value, decimals=0):
    """Décimal localisé : 1234.567, 2 → '1 234,57'."""
    try:
        return format_number(value, decimals=int(decimals))
    except (TypeError, ValueError):
        return str(value)