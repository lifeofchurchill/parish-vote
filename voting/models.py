"""
Database tables for the election check-in system.

Member          -> a copy of a person from the church's Excel export
OrganizerProfile-> links an organizer's login to the centre they work at
VoteCheckIn     -> proof that a member has voted (one per member, ever)
"""
from datetime import timedelta

from django.conf import settings
from django.db import models


# The two polling centres: short code saved in the database, full name shown on screen
CENTRE_CHOICES = [
    ("STM", "St. Thomas More, Achimota"),
    ("TMJF", "Ss. Thomas More & John Fisher, New Achimota"),
]

# Every voting session across both centres
SESSION_CHOICES = [
    ("0630", "After 6:30 a.m. Mass"),
    ("0700", "After 7:00 a.m. Mass"),
    ("0930", "After 9:30 a.m. Mass"),
]

# Which sessions run at which centre (section 8 of the church's document)
SESSIONS_BY_CENTRE = {
    "STM": ["0700", "0930"],
    "TMJF": ["0630", "0930"],
}


def eligible_dob_range():
    """
    Return (earliest, latest) date of birth for an eligible voter.

    For election day 29 Nov 2026 and ages 13-38 this gives
    30 Nov 1987 to 29 Nov 2013.
    """
    day = settings.ELECTION_DATE
    # Youngest allowed: turned 13 on or before election day
    latest = day.replace(year=day.year - settings.VOTER_MIN_AGE)
    # Oldest allowed: still 38, i.e. has NOT turned 39 by election day
    earliest = day.replace(year=day.year - settings.VOTER_MAX_AGE - 1) + timedelta(days=1)
    return earliest, latest


class MemberQuerySet(models.QuerySet):
    """Reusable filters, so every page asks for 'eligible' the same way."""

    def eligible(self):
        # Members whose date of birth falls inside the 13-38 range
        earliest, latest = eligible_dob_range()
        return self.filter(date_of_birth__range=(earliest, latest))

    def needs_checking(self):
        # Members with no date of birth: we can't tell if they're eligible
        return self.filter(date_of_birth__isnull=True)


class Member(models.Model):
    # The member's ID in the church software; lets a re-import update instead of duplicate
    church_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=150)
    # Optional because some church records may be missing it
    date_of_birth = models.DateField(null=True, blank=True)
    # Stored as digits only, e.g. "0241234567"
    phone = models.CharField(max_length=20, blank=True)
    # Empty society = non-aligned youth
    society = models.CharField(max_length=100, blank=True)
    parish = models.CharField(max_length=100, blank=True)
    # Last time this row was created or updated by an import
    imported_at = models.DateTimeField(auto_now=True)

    # Lets us write Member.objects.eligible()
    objects = MemberQuerySet.as_manager()

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.church_id})"

    @property
    def age(self):
        """Age on election day (None if no date of birth)."""
        if not self.date_of_birth:
            return None
        day = settings.ELECTION_DATE
        dob = self.date_of_birth
        # Subtract 1 if their birthday hasn't come yet in the election year
        before_birthday = (day.month, day.day) < (dob.month, dob.day)
        return day.year - dob.year - before_birthday

    @property
    def society_label(self):
        """What organizers see: the society name, or 'Non-aligned'."""
        return self.society or "Non-aligned"

    @property
    def masked_phone(self):
        """Show only the start and end of the number, e.g. 024•••••67."""
        if len(self.phone) < 6:
            return self.phone
        return self.phone[:3] + "•" * (len(self.phone) - 5) + self.phone[-2:]

    @property
    def vote_record(self):
        """This member's check-in, or None if they haven't voted yet."""
        return getattr(self, "checkin", None)


class OrganizerProfile(models.Model):
    # One profile per login; tells us which centre this organizer works at
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organizer"
    )
    centre = models.CharField(max_length=10, choices=CENTRE_CHOICES)

    def __str__(self):
        return f"{self.user.username} @ {self.get_centre_display()}"


class VoteCheckIn(models.Model):
    # OneToOne = the DATABASE allows only one check-in per member.
    # If both centres tick the same person at the same second, the second one fails.
    member = models.OneToOneField(Member, on_delete=models.PROTECT, related_name="checkin")
    centre = models.CharField(max_length=10, choices=CENTRE_CHOICES)
    session = models.CharField(max_length=10, choices=SESSION_CHOICES)
    # Who ticked them; PROTECT stops anyone deleting an organizer who has ticked people
    ticked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticks"
    )
    ticked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ticked_at"]

    def __str__(self):
        return f"{self.member.full_name} voted at {self.get_centre_display()}"