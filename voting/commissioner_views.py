"""
Pages for the Electoral Commissioner: live turnout, adding missing dates of birth,
and undoing a tick made by mistake.

Only staff accounts can open them (the "Staff status" box on the user in the admin).
Officials who try get a "This page is for the Electoral Commissioner" page instead.
"""
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DateOfBirthForm, UndoTickForm
from .models import Election, Member, OrganizerProfile, TickUndo, VoteCheckIn, VotingSession
# The same search rules as the check-in page, so searching feels the same everywhere
from .views import MAX_RESULTS, MIN_NAME_LETTERS, MIN_PHONE_DIGITS, _initials, _who

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


# ---------- Needs checking: members with no date of birth ----------

def _needs_checking_context(election):
    """Everything the Needs checking page shows."""
    # Still missing a date of birth
    missing = list(Member.objects.needs_checking().order_by("full_name"))
    for member in missing:
        member.initials = _initials(member.full_name)

    # Dates added on this page, newest first, with what each means for this election
    added = list(
        Member.objects.filter(dob_added_at__isnull=False)
        .select_related("dob_added_by")
        .order_by("-dob_added_at")
    )
    eligible_ids = set()
    if election:
        eligible_ids = set(
            Member.objects.eligible(election)
            .filter(pk__in=[m.pk for m in added])
            .values_list("pk", flat=True)
        )
    for member in added:
        member.initials = _initials(member.full_name)
        member.age = member.age_on(election.date) if election else None
        member.can_vote = member.pk in eligible_ids
        member.added_by_name = _who(member.dob_added_by) if member.dob_added_by else "the admin"

    return {
        "role_label": ROLE_LABEL,
        "election": election,
        "missing": missing,
        "added": added,
        "today": timezone.localdate(),   # the latest date the date picker allows
    }


@commissioner_required
def needs_checking(request):
    """Members the system can't check against the age rule, and the dates added here."""
    election = Election.objects.active()
    return render(request, "voting/needs_checking.html", _needs_checking_context(election))


@commissioner_required
@require_POST
def add_date_of_birth(request, member_id):
    """Save a date of birth typed on the Needs checking page."""
    election = Election.objects.active()
    # Only members with no date, or one added here before. Dates from the church's
    # records can't be changed from this page (the admin is the place for that).
    member = get_object_or_404(
        Member.objects.filter(Q(date_of_birth__isnull=True) | Q(dob_added_at__isnull=False)),
        pk=member_id,
    )

    form = DateOfBirthForm(request.POST)
    if not form.is_valid():
        # Show the page again with the error on this person's card
        context = _needs_checking_context(election)
        context.update({"error_member_id": member.pk, "error_form": form})
        return render(request, "voting/needs_checking.html", context)

    member.date_of_birth = form.cleaned_data["date_of_birth"]
    member.dob_added_by = request.user
    member.dob_added_at = timezone.now()
    member.save(update_fields=["date_of_birth", "dob_added_by", "dob_added_at"])

    # Say straight away what the new date means for this election
    name = member.full_name
    if election is None:
        messages.success(request, f"Saved {name}'s date of birth.")
    elif Member.objects.eligible(election).filter(pk=member.pk).exists():
        messages.success(
            request,
            f"Saved. {name} is {member.age_on(election.date)} on election day, "
            f"so officials can now find and tick them.",
        )
    else:
        messages.error(
            request,
            f"Saved, but {name} is {member.age_on(election.date)} on election day: outside the "
            f"age rule ({election.age_rule}), so they can't vote in this election.",
        )
    return redirect("voting:needs_checking")


# ---------- Undoing a tick ----------

def _search_ticks(election, query):
    """
    Search the people TICKED in this election, by name or phone (same rules as check-in).
    Returns (ticks, problem). problem is None, "short_name" or "short_phone".
    """
    compact = query.replace(" ", "").replace("+", "").replace("-", "")
    ticks = VoteCheckIn.objects.filter(election=election).select_related(
        "member", "session__centre", "ticked_by"
    )

    if compact.isdigit():
        if len(compact) < MIN_PHONE_DIGITS:
            return [], "short_phone"
        digits = "0" + compact[3:] if compact.startswith("233") and len(compact) > 4 else compact
        ticks = ticks.filter(Q(member__phone__contains=digits) | Q(member__other_phones__contains=digits))
    else:
        if len(compact) < MIN_NAME_LETTERS:
            return [], "short_name"
        for word in query.split():
            ticks = ticks.filter(member__full_name__icontains=word)

    return list(ticks.order_by("member__full_name")[: MAX_RESULTS + 1]), None


@commissioner_required
def undo_search(request):
    """Find a ticked voter, and see the log of every tick undone in this election."""
    election = Election.objects.active()
    if election is None:
        return render(request, "voting/undo.html", {"role_label": ROLE_LABEL, "no_election": True})

    context = {"role_label": ROLE_LABEL}
    query = request.GET.get("q", "").strip()
    if query:
        ticks, search_problem = _search_ticks(election, query)
        for tick in ticks:
            tick.member.age = tick.member.age_on(election.date)
            tick.member.initials = _initials(tick.member.full_name)
        context.update({
            "query": query,
            "search_problem": search_problem,
            "results": ticks[:MAX_RESULTS],
            "more_results": len(ticks) > MAX_RESULTS,
        })

    # The permanent log for this election, newest first
    context["log"] = TickUndo.objects.filter(election=election).select_related(
        "member", "session__centre", "ticked_by", "undone_by"
    )
    return render(request, "voting/undo.html", context)


@commissioner_required
def undo_tick(request, checkin_id):
    """
    GET:  the confirm screen, with the tick's details and a box for the reason.
    POST: save the reason in the log and remove the tick, both or neither.
    """
    election = Election.objects.active()
    if election is None:
        return redirect("voting:undo")   # that page explains there's no open election
    query = request.GET.get("q", "")
    tick = (
        VoteCheckIn.objects.filter(pk=checkin_id, election=election)
        .select_related("member", "session__centre", "ticked_by")
        .first()
    )
    if tick is None:
        # Already undone (perhaps by someone else a moment ago), or not in this election
        messages.error(request, "That tick has already been undone, so there was nothing to remove.")
        return redirect("voting:undo")

    form = UndoTickForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # atomic(): the log entry and the removal happen together, or not at all
        with transaction.atomic():
            # Lock the tick while we work, so two people can't undo it at the same moment.
            # (PostgreSQL honours this; SQLite simply runs one write at a time anyway.)
            locked = VoteCheckIn.objects.select_for_update().filter(pk=tick.pk).first()
            if locked is None:
                messages.error(request, "That tick has already been undone, so there was nothing to remove.")
                return redirect("voting:undo")
            TickUndo.objects.create(
                election=tick.election,
                member=tick.member,
                session=tick.session,
                ticked_by=tick.ticked_by,
                ticked_at=tick.ticked_at,
                undone_by=request.user,
                reason=form.cleaned_data["reason"],
            )
            locked.delete()
        messages.success(
            request,
            f"Tick undone. {tick.member.full_name} can be ticked again; your reason is in the undo log.",
        )
        return redirect("voting:undo")

    # GET, or the reason was missing/too short: show the confirm screen (with the error)
    tick.member.age = tick.member.age_on(election.date)
    tick.member.initials = _initials(tick.member.full_name)
    tick.ticked_by_name = _who(tick.ticked_by)
    return render(request, "voting/undo_confirm.html", {
        "role_label": ROLE_LABEL,
        "tick": tick,
        "form": form,
        "query": query,
    })