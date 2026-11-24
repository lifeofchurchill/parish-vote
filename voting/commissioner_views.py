"""
Pages for the Electoral Commissioner: live turnout now; fixing mistakes next.

Only staff accounts can open them (the "Staff status" box on the user in the admin).
Officials who try get a "This page is for the Electoral Commissioner" page instead.
"""
from datetime import timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q
from django.shortcuts import render
from django.utils import timezone

from .models import Election, Member, OrganizerProfile, VoteCheckIn, VotingSession

# Shown in the app bar instead of a polling centre
ROLE_LABEL = "Electoral Commissioner"

# How many of the latest ticks to list on the dashboard (overall, and for each centre)
RECENT_TICKS = 15

# "In the last 10 minutes": shows whether queues are building or things have gone quiet.
# An official who hasn't ticked anyone for this long is shown as "quiet".
PACE_MINUTES = 10


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


def _officials_by_centre(election, centre_ids, now):
    """
    Every active official at these centres, with how many voters they've ticked in this
    election and when they last ticked someone. Grouped as {centre id: [officials]}.
    One query: the database does the counting.
    """
    in_this_election = Q(user__ticks__election=election)
    officials = (
        OrganizerProfile.objects.filter(centre_id__in=centre_ids, user__is_active=True)
        .select_related("user")
        .annotate(
            ticked=Count("user__ticks", filter=in_this_election),
            last_tick=Max("user__ticks__ticked_at", filter=in_this_election),
        )
        .order_by("-ticked", "user__first_name", "user__username")
    )

    grouped = {centre_id: [] for centre_id in centre_ids}
    for official in officials:
        official.name = official.user.get_full_name() or official.user.username
        if official.last_tick is None:
            official.status = "idle"            # hasn't ticked anyone yet
        else:
            official.quiet_minutes = int((now - official.last_tick).total_seconds() // 60)
            # Ticked someone recently = active; otherwise quiet (worth a phone call?)
            official.status = "active" if official.quiet_minutes < PACE_MINUTES else "quiet"
        grouped[official.centre_id].append(official)
    return grouped


@commissioner_required
def dashboard(request):
    """Live turnout for the active election: totals, each centre and session, latest ticks."""
    election = Election.objects.active()
    if election is None:
        return render(request, "voting/dashboard.html", {"role_label": ROLE_LABEL, "no_election": True})

    now = timezone.now()

    # Headline numbers
    eligible = Member.objects.eligible(election).count()
    ticks = VoteCheckIn.objects.filter(election=election)
    voted = ticks.count()
    turnout = voted * 100 / eligible if eligible else 0     # exact, e.g. 27.79
    percent = round(turnout)                                 # shown as a whole number, e.g. 28

    # Ticks in the last few minutes (the dashboard's "pace")
    recent_pace = ticks.filter(ticked_at__gte=now - timedelta(minutes=PACE_MINUTES)).count()

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
            "pk": session.centre.pk,
            "name": session.centre.name,
            # Short name for the filter buttons: "St. Thomas More, Achimota" -> "St. Thomas More"
            "short_name": session.centre.name.split(",")[0],
            "total": 0,
            "sessions": [],
        })
        centre["total"] += session.ticked
        centre["sessions"].append(session)

    # Each centre's officials, and the time of the centre's latest tick
    officials = _officials_by_centre(election, list(centres), now)
    last_tick_at = dict(
        ticks.order_by().values("session__centre").annotate(last=Max("ticked_at"))
        .values_list("session__centre", "last")
    )
    for centre in centres.values():
        centre["officials"] = officials[centre["pk"]]
        centre["last_tick"] = last_tick_at.get(centre["pk"])

    # Latest ticks: the newest overall, plus the newest at each centre, so that
    # filtering "Latest ticks" to one centre still shows a full list for it
    related = ("member", "session__centre", "ticked_by")
    overall = list(ticks.select_related(*related)[:RECENT_TICKS])
    recent = {tick.pk: tick for tick in overall}
    for centre_id in centres:
        for tick in ticks.filter(session__centre_id=centre_id).select_related(*related)[:RECENT_TICKS]:
            recent.setdefault(tick.pk, tick)
    overall_ids = {tick.pk for tick in overall}
    for tick in recent.values():
        tick.in_overall = tick.pk in overall_ids   # the others are only shown when filtering
    recent = sorted(recent.values(), key=lambda tick: tick.ticked_at, reverse=True)

    # Members with no date of birth can't be checked against an age rule
    has_age_rule = election.min_age is not None or election.max_age is not None
    needs_checking = Member.objects.needs_checking().count() if has_age_rule else 0

    return render(request, "voting/dashboard.html", {
        "role_label": ROLE_LABEL,
        "eligible": eligible,
        "voted": voted,
        "remaining": max(eligible - voted, 0),
        "percent": percent,
        # How much of the rose window is lit. A string with a dot ("27.79"), because it goes
        # into an SVG attribute, which must never get a comma from number formatting.
        "turnout_exact": f"{min(turnout, 100):.2f}",
        "recent_pace": recent_pace,
        "pace_minutes": PACE_MINUTES,
        "centres": list(centres.values()),
        "recent": recent,
        "recent_max": RECENT_TICKS,
        "needs_checking": needs_checking,
        "updated_at": now,
    })