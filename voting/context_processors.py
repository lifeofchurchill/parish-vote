"""
Context processors add variables to EVERY template automatically.
"""
from django.utils.functional import SimpleLazyObject

from .models import Election


def active_election(request):
    """
    Makes {{ election }} available in every template: the active election, or None.

    SimpleLazyObject means the database is only asked when a template actually
    uses {{ election }}, so pages that don't need it cost nothing extra.
    """
    return {"election": SimpleLazyObject(Election.objects.active)}