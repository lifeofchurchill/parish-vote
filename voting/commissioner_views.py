"""
Pages for the Electoral Commissioner: live turnout now; fixing mistakes next.

Only staff accounts can open them (the "Staff status" box on the user in the admin).
Officials who try get a "This page is for the Electoral Commissioner" page instead.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from .models import Election, Member, VoteCheckIn, VotingSession

# Shown in the app bar instead of a polling centre
ROLE_LABEL = "Electoral Commissioner"

# How many of the latest ticks to list on the dashboard
RECENT_TICKS = 15


def commissioner_required(view):
    """
    Decorator: the user must be signed in AND be staff.
    Not signed in -> sent to the sign-in page. Signed in but not staff -> 403 page.
    """
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


@commissioner_required
def dashboard(request):
    """Live turnout for the active election: totals, each centre and session, latest ticks."""
    election = Election.objects.active()
    if election is None:
        return render(request, "voting/dashboard.html", {"role_label": ROLE_LABEL, "no_election": True})

    # Headline numbers
    eligible = Member.objects.eligible(election).count()
    voted = VoteCheckIn.objects.filter(election=election).count()
    percent = round(voted * 100 / eligible) if eligible else 0

    # Every session of this election with its tick count (counted by the database in one query)
    sessions = list(
        VotingSession.objects.filter(election=election)
        .select_related("centre")
        .annotate(ticked=Count("checkins"))
        .order_by("centre__name", "starts_at", "label")
    )
    # Bar lengths are relative to the busiest session, so the busiest one is a full bar
    busiest = max((s.ticked for s in sessions), default=0)

    # Group the sessions under their centre, adding up each centre's total
    centres = {}
    for session in sessions:
        session.bar = round(session.ticked * 100 / busiest) if busiest else 0
        centre = centres.setdefault(session.centre.pk, {
            "name": session.centre.name, "total": 0, "sessions": [],
        })
        centre["total"] += session.ticked
        centre["sessions"].append(session)

    # The latest ticks, newest first (VoteCheckIn's default ordering is -ticked_at)
    recent = (
        VoteCheckIn.objects.filter(election=election)
        .select_related("member", "session__centre", "ticked_by")[:RECENT_TICKS]
    )

    # Members with no date of birth can't be checked against an age rule
    has_age_rule = election.min_age is not None or election.max_age is not None
    needs_checking = Member.objects.needs_checking().count() if has_age_rule else 0

    return render(request, "voting/dashboard.html", {
        "role_label": ROLE_LABEL,
        "eligible": eligible,
        "voted": voted,
        "remaining": max(eligible - voted, 0),
        "percent": percent,
        "centres": list(centres.values()),
        "recent": recent,
        "needs_checking": needs_checking,
        "updated_at": timezone.now(),
    })