"""
Database tables for the parish election check-in system.

Election        -> one election (name, date, age rule); exactly one is "active" at a time
PollingCentre   -> a place where people vote (e.g. St. Thomas More, Achimota)
VotingSession   -> a voting window at a centre for one election (e.g. After 7:00 a.m. Mass)
Member          -> a person copied from the church's CSV export
OrganizerProfile-> links an official's login to the centre they work at
VoteCheckIn     -> proof that a member has voted in an election (one per member per election)
TickUndo        -> permanent record of a tick the Electoral Commissioner removed, and why
"""
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def years_before(day, years):
    """The same calendar day `years` earlier. 29 Feb falls back to 28 Feb in non-leap years."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def age_on(dob, day):
    """Age in whole years on `day` (None if no date of birth)."""
    if not dob:
        return None
    # Subtract 1 if their birthday hasn't come yet that year
    before_birthday = (day.month, day.day) < (dob.month, dob.day)
    return day.year - dob.year - before_birthday


# ---------------------------------------------------------------- elections

class ElectionQuerySet(models.QuerySet):
    def active(self):
        """The election currently being run, or None."""
        return self.filter(is_active=True).first()


class Election(models.Model):
    name = models.CharField(max_length=150)  # e.g. "Parish Youth Council Elections 2026"
    date = models.DateField()
    # Optional words shown after the date, e.g. "the First Sunday of Advent"
    date_note = models.CharField(max_length=100, blank=True, default="")
    # Leave an age empty for "no limit" (e.g. an adults-only election has only a minimum)
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    # The whole system follows the active election
    is_active = models.BooleanField(default=False)

    objects = ElectionQuerySet.as_manager()

    class Meta:
        ordering = ["-date"]
        constraints = [
            # The database itself refuses a second active election
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name="only_one_active_election",
                violation_error_message="Only one election can be active. Untick the other one first.",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        # Runs when the form in the admin is saved: catch impossible age rules
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValidationError("Minimum age can't be higher than maximum age.")

    def dob_range(self):
        """
        (earliest, latest) date of birth for an eligible voter; either can be None (no limit).
        For 29 Nov 2026 and ages 13-38: (30 Nov 1987, 29 Nov 2013).
        """
        # Youngest allowed: reached min_age on or before election day
        latest = years_before(self.date, self.min_age) if self.min_age is not None else None
        # Oldest allowed: has NOT yet reached max_age + 1 on election day
        earliest = (
            years_before(self.date, self.max_age + 1) + timedelta(days=1)
            if self.max_age is not None else None
        )
        return earliest, latest

    @property
    def age_rule(self):
        """Readable age rule, e.g. '13 to 38', '18 and over', 'any age'."""
        if self.min_age is not None and self.max_age is not None:
            return f"{self.min_age} to {self.max_age}"
        if self.min_age is not None:
            return f"{self.min_age} and over"
        if self.max_age is not None:
            return f"up to {self.max_age}"
        return "any age"


class PollingCentre(models.Model):
    name = models.CharField(max_length=150, unique=True)  # e.g. "St. Thomas More, Achimota"

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class VotingSession(models.Model):
    # Deleting an election deletes its sessions too (CASCADE)...
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="sessions")
    # ...but a centre that still has sessions can't be deleted (PROTECT)
    centre = models.ForeignKey(PollingCentre, on_delete=models.PROTECT, related_name="sessions")
    label = models.CharField(max_length=100)  # e.g. "After 7:00 a.m. Mass"
    # Used only to list sessions in time order
    starts_at = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["starts_at", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["election", "centre", "label"], name="unique_session_per_centre"
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.centre})"


# ---------------------------------------------------------------- members

class MemberQuerySet(models.QuerySet):
    """Reusable filters, so every page asks for 'eligible' the same way."""

    def eligible(self, election):
        """Members who meet this election's age rule."""
        earliest, latest = election.dob_range()
        members = self
        # Any age limit means we need a date of birth to decide
        if earliest or latest:
            members = members.filter(date_of_birth__isnull=False)
        if earliest:
            members = members.filter(date_of_birth__gte=earliest)
        if latest:
            members = members.filter(date_of_birth__lte=latest)
        return members

    def needs_checking(self):
        """Members with no date of birth: can't tell if they meet an age rule."""
        return self.filter(date_of_birth__isnull=True)


class Member(models.Model):
    # "id" column in the church export; lets a re-import update instead of duplicate
    church_id = models.CharField(max_length=50, unique=True)
    # "name" column. Word order varies in the church data, so search matches words in any order
    full_name = models.CharField(max_length=150)
    # "birthDate" column. Optional because some church records may be missing it
    date_of_birth = models.DateField(null=True, blank=True)
    # First number from the "phone" column, cleaned to digits, e.g. "0271394092"
    phone = models.CharField(max_length=20, blank=True, default="")
    # Any extra numbers from the same cell, space-separated. Used only for searching
    other_phones = models.CharField(max_length=100, blank=True, default="")
    # "community" column, e.g. "Christian Village". Helps officials tell people apart
    community = models.CharField(max_length=100, blank=True, default="")
    # Last time this row was created or updated by an import
    imported_at = models.DateTimeField(auto_now=True)
    # Filled in when the Electoral Commissioner adds a missing date of birth on the
    # "Needs checking" page: who and when. A re-import keeps that date, unless the
    # church's export now has a readable one (the church's record wins).
    dob_added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="dobs_added",
    )
    dob_added_at = models.DateTimeField(null=True, blank=True)

    # Lets us write Member.objects.eligible(election)
    objects = MemberQuerySet.as_manager()

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.church_id})"

    def age_on(self, day):
        """Age on a given day, e.g. member.age_on(election.date)."""
        return age_on(self.date_of_birth, day)

    @property
    def community_label(self):
        """What officials see: the community name, or a clear 'not listed'."""
        return self.community or "No community listed"

    @property
    def masked_phone(self):
        """Show only the start and end of the number, e.g. 027•••••92."""
        if len(self.phone) < 6:
            return self.phone
        return self.phone[:3] + "•" * (len(self.phone) - 5) + self.phone[-2:]


# ---------------------------------------------------------------- officials and ticks

class OrganizerProfile(models.Model):
    # One profile per login; tells us which centre this official works at
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organizer"
    )
    centre = models.ForeignKey(PollingCentre, on_delete=models.PROTECT, related_name="officials")

    def __str__(self):
        return f"{self.user.username} @ {self.centre}"


class VoteCheckIn(models.Model):
    election = models.ForeignKey(Election, on_delete=models.PROTECT, related_name="checkins")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="checkins")
    # The session also tells us the centre (session.centre)
    session = models.ForeignKey(VotingSession, on_delete=models.PROTECT, related_name="checkins")
    # Who ticked them; PROTECT stops anyone deleting an official who has ticked people
    ticked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticks"
    )
    ticked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ticked_at"]
        constraints = [
            # THE double-vote protection: one check-in per member PER ELECTION.
            # If both centres tick the same person at the same second, the second one fails.
            models.UniqueConstraint(
                fields=["election", "member"], name="one_vote_per_member_per_election"
            ),
        ]

    def __str__(self):
        return f"{self.member.full_name} voted in {self.election}"


class TickUndo(models.Model):
    """
    A tick the Electoral Commissioner removed, kept forever.

    Undoing deletes the VoteCheckIn (so the member can be ticked again), but first
    every detail of it is copied here, with who undid it, when, and why.
    Nothing in the app edits or deletes these rows: the admin shows them read-only.
    """
    election = models.ForeignKey(Election, on_delete=models.PROTECT, related_name="undos")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="undos")

    # Copied from the removed tick: where, who and when
    session = models.ForeignKey(VotingSession, on_delete=models.PROTECT, related_name="undos")
    ticked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticks_undone"
    )
    ticked_at = models.DateTimeField()

    # The undo itself
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="undos"
    )
    undone_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()

    class Meta:
        ordering = ["-undone_at"]

    def __str__(self):
        return f"{self.member.full_name}: tick undone"