"""
Context processors pour InsightApp.

Ces fonctions injectent des variables dans le contexte de TOUS les templates,
sans avoir à les passer explicitement depuis chaque vue.
"""
from django.conf import settings


def company_processor(request):
    """
    Expose les informations de l'entreprise (définies dans settings.py)
    à tous les templates.

    Utilisation dans un template :
        {{ company.name }}
        {{ company.email }}
        {{ company.phone }}
        {{ company.address }}
        {{ company.website }}
    """
    return {
        "company": {
            "name": getattr(settings, "COMPANY_NAME", "InsightBoard"),
            "address": getattr(settings, "COMPANY_ADDRESS", ""),
            "phone": getattr(settings, "COMPANY_PHONE", ""),
            "email": getattr(settings, "COMPANY_EMAIL", ""),
            "website": getattr(settings, "COMPANY_WEBSITE", ""),
        }
    }