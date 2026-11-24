"""
Views for the check-in pages used by election officials.

Flow on election day:
  1. The official signs in. Their account is tied to one polling centre.
  2. They choose the session (which Mass they're checking voters in after).
  3. They search for a voter by name or phone.
  4. They confirm and tick the voter.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Election, Member, VoteCheckIn, VotingSession

# Key used to remember the official's chosen session between page loads
# (stored in Django's session, i.e. tied to this browser's sign-in)
SESSION_KEY = "voting_session_id"

# Search rules
MIN_NAME_LETTERS = 2     # "a" would match half the parish
MIN_PHONE_DIGITS = 4     # "02" would match almost every number
MAX_RESULTS = 25         # keeps the page fast on a phone

# If the same official ticks the same person twice within this many seconds,
# it's a double-tap on a slow connection, not a second vote
DOUBLE_TAP_SECONDS = 60


# ---------- small helpers ----------

def _get_profile(request):
    """The official's profile (which centre they work at), or None if not set up."""
    return getattr(request.user, "organizer", None)


def _sessions_for(election, profile):
    """This election's voting sessions at the official's own centre, in time order."""
    return VotingSession.objects.filter(election=election, centre=profile.centre)


def _current_session(request, election, profile):
    """
    The session the official picked, or None.
    Checked against the database every time, so a session from an old election
    or another centre can never be used, even if it's still remembered.
    """
    session_id = request.session.get(SESSION_KEY)
    if session_id is None:
        return None
    return _sessions_for(election, profile).filter(pk=session_id).first()


def _suggested_session(election, sessions):
    """
    On election day, the session that started most recently: the one marked "Now".
    At 9:45 on election morning that's "After 9:30 a.m. Mass". Any other day: None.
    """
    if timezone.localdate() != election.date:
        return None
    now = timezone.localtime().time()
    started = [s for s in sessions if s.starts_at and s.starts_at <= now]
    return started[-1] if started else None


def _initials(name):
    """'Tetteh Anita' -> 'TA', 'Ama' -> 'A'. Used for the circle on each result card."""
    words = name.split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    # First letter of the first word + first letter of the last word
    return (words[0][0] + words[-1][0]).upper()


def _who(user):
    """An official's display name: full name if set, otherwise username."""
    return user.get_full_name() or user.username


def _clock(moment):
    """A stored time shown in Ghana time, e.g. '9:41 a.m.'."""
    local = timezone.localtime(moment)
    return local.strftime("%I:%M").lstrip("0") + (" a.m." if local.hour < 12 else " p.m.")


def _search(election, query):
    """
    Search eligible members by phone number or by name.
    Returns (members, problem). problem is None, "short_name" or "short_phone".
    """
    compact = query.replace(" ", "").replace("+", "").replace("-", "")

    if compact.isdigit():
        # Phone search: "+233 24 123 4567" and "024 123 4567" both work
        if len(compact) < MIN_PHONE_DIGITS:
            return [], "short_phone"
        digits = "0" + compact[3:] if compact.startswith("233") and len(compact) > 4 else compact
        members = Member.objects.eligible(election).filter(
            Q(phone__contains=digits) | Q(other_phones__contains=digits)
        )
    else:
        # Name search: every word must appear somewhere in the name, in any order,
        # so "anita tetteh" finds "Tetteh Anita"
        if len(compact) < MIN_NAME_LETTERS:
            return [], "short_name"
        members = Member.objects.eligible(election)
        for word in query.split():
            members = members.filter(full_name__icontains=word)

    # Fetch each member's check-in for THIS election in one extra query (not one per member),
    # with the session, centre and official who ticked them
    members = members.prefetch_related(
        Prefetch(
            "checkins",
            queryset=VoteCheckIn.objects.filter(election=election)
                                        .select_related("session__centre", "ticked_by"),
            to_attr="records",
        )
    )
    # One more than we show, so we know whether there were more matches
    return list(members[: MAX_RESULTS + 1]), None


# ---------- pages ----------

@login_required
def checkin(request):
    """Main check-in page: session picker, live session panel, search and results."""
    election = Election.objects.active()
    profile = _get_profile(request)

    # The Electoral Commissioner (a staff account with no polling centre) belongs on the dashboard
    if profile is None and request.user.is_staff:
        return redirect("voting:dashboard")

    # Anything that stops check-in from starting gets its own clear message
    if election is None:
        return render(request, "voting/checkin.html", {"problem": "no_election"})
    if profile is None:
        return render(request, "voting/checkin.html", {"problem": "no_centre"})

    # Each session with .ticked = how many voters were ticked in it (one query, counted by the database)
    sessions = list(_sessions_for(election, profile).annotate(ticked=Count("checkins")))
    if not sessions:
        return render(request, "voting/checkin.html", {
            "problem": "no_sessions",
            "centre_label": profile.centre.name,
        })

    current = _current_session(request, election, profile)
    context = {
        "centre_label": profile.centre.name,   # shown in the app bar
        "sessions": sessions,
        "current_session": current,
        "suggested_session": _suggested_session(election, sessions),
        # Live numbers for the session panel
        "session_total": next((s.ticked for s in sessions if current and s.pk == current.pk), 0),
        "centre_total": VoteCheckIn.objects.filter(
            election=election, session__centre=profile.centre
        ).count(),
    }

    # Search only once a session is chosen
    query = request.GET.get("q", "").strip()
    if current and query:
        members, search_problem = _search(election, query)
        for member in members:
            # Values the result card needs, worked out once here instead of in the template
            member.age = member.age_on(election.date)
            member.initials = _initials(member.full_name)
            member.record = member.records[0] if member.records else None
        context.update({
            "query": query,
            "search_problem": search_problem,
            "results": members[:MAX_RESULTS],
            "more_results": len(members) > MAX_RESULTS,
        })

    return render(request, "voting/checkin.html", context)


@login_required
@require_POST
def set_session(request):
    """Save the official's chosen session, or clear it so the picker shows again."""
    election = Election.objects.active()
    profile = _get_profile(request)
    session_id = request.POST.get("session", "")

    # Only accept a session that belongs to the active election AND this official's centre
    valid = (
        election is not None
        and profile is not None
        and session_id.isdigit()
        and _sessions_for(election, profile).filter(pk=session_id).exists()
    )
    if valid:
        request.session[SESSION_KEY] = int(session_id)
    else:
        # "Change session" sends an empty value: forget the session and show the picker
        request.session.pop(SESSION_KEY, None)
    return redirect("voting:checkin")


@login_required
def tick(request, member_id):
    """
    GET:  the confirm screen ("Is this the person in front of you?").
    POST: record that the member has voted in the active election.
    """
    election = Election.objects.active()
    profile = _get_profile(request)
    if election is None or profile is None:
        # The check-in page explains what's wrong
        return redirect("voting:checkin")

    session = _current_session(request, election, profile)
    if session is None:
        messages.error(request, "Choose your session before ticking voters.")
        return redirect("voting:checkin")

    # Only eligible members can be ticked, even if someone types another id into the address bar
    member = get_object_or_404(Member.objects.eligible(election), pk=member_id)

    if request.method == "POST":
        try:
            # atomic(): if the insert is refused, the database is left exactly as it was
            with transaction.atomic():
                VoteCheckIn.objects.create(
                    election=election,
                    member=member,
                    session=session,
                    ticked_by=request.user,
                )
        except IntegrityError:
            # The one-vote-per-member-per-election rule refused it: they're already ticked
            existing = VoteCheckIn.objects.select_related("session__centre", "ticked_by").get(
                election=election, member=member
            )
            seconds_ago = (timezone.now() - existing.ticked_at).total_seconds()
            if existing.ticked_by_id == request.user.id and seconds_ago < DOUBLE_TAP_SECONDS:
                # This official's own double-tap: the first tap worked, so report success
                messages.success(request, f"{member.full_name} is ticked. Hand over the ballot paper.")
            else:
                messages.error(
                    request,
                    f"STOP: {member.full_name} has already voted at {existing.session.centre.name}, "
                    f"{_clock(existing.ticked_at)}, ticked by {_who(existing.ticked_by)}. "
                    f"Do not give a ballot paper.",
                )
        else:
            messages.success(request, f"{member.full_name} is ticked. Hand over the ballot paper.")
        # Redirect after POST: refreshing the page can't send the tick again,
        # and the search is cleared for the next voter
        return redirect("voting:checkin")

    # GET: the confirm screen. Someone may have ticked them since the search, so check again.
    existing = (
        VoteCheckIn.objects.filter(election=election, member=member)
        .select_related("session__centre", "ticked_by")
        .first()
    )
    member.age = member.age_on(election.date)
    member.initials = _initials(member.full_name)
    return render(request, "voting/confirm.html", {
        "centre_label": profile.centre.name,
        "member": member,
        "session": session,
        "existing": existing,
        "query": request.GET.get("q", ""),   # so "Back to results" returns to the same search
    })