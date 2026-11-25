"""
Forms for the parish election pages.
"""
from django import forms
from django.utils import timezone

from .cleaning import clean_name, clean_phones
from .models import age_on


def _check_birth_date(dob):
    """Errors any date of birth form should catch: a date in the future, or a typo'd year."""
    if dob > timezone.localdate():
        raise forms.ValidationError("That date is in the future.")
    if dob.year < 1900:
        raise forms.ValidationError("That date is too far back. Check the year.")
    return dob


class UndoTickForm(forms.Form):
    """The one thing the Commissioner must give before a tick is removed: the reason."""

    reason = forms.CharField(
        # strip=True (the default) means "          " counts as empty
        min_length=10,
        max_length=500,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "undo-reason",
            "aria-describedby": "reason-help",
            "placeholder": "e.g. The official ticked the wrong Ama Mensah (age 25). "
                           "The voter was Ama Mensah, age 17, Christian Village.",
        }),
        error_messages={
            "required": "Write why this tick is being undone.",
            "min_length": "Say a little more (at least 10 characters), so the log makes sense later.",
            "max_length": "Keep it under 500 characters.",
        },
    )


class DateOfBirthForm(forms.Form):
    """A missing date of birth, added by the Commissioner on the Needs checking page."""

    # On phones type="date" opens the date picker; it always sends the date as 2026-11-29
    date_of_birth = forms.DateField(
        error_messages={
            "required": "Enter their date of birth.",
            "invalid": "That isn't a real date. Pick it from the calendar, or type it as day/month/year.",
        },
    )

    def clean_date_of_birth(self):
        return _check_birth_date(self.cleaned_data["date_of_birth"])


class AddMemberForm(forms.Form):
    """
    Someone who isn't on the church list, added by an official on election day.
    The date of birth is required: it's the only way to check the age rule.
    Phone and community are optional (some 13-year-olds don't have a phone).
    """

    full_name = forms.CharField(
        max_length=150,
        error_messages={
            "required": "Enter their full name.",
            "max_length": "That name is too long. Keep it under 150 characters.",
        },
    )
    date_of_birth = forms.DateField(
        error_messages={
            "required": "Enter their date of birth: it's how we check the age rule.",
            "invalid": "That isn't a real date. Pick it from the calendar.",
        },
    )
    phone = forms.CharField(required=False, max_length=30)
    community = forms.CharField(
        required=False,
        max_length=100,
        error_messages={"max_length": "Keep the community under 100 characters."},
    )

    def __init__(self, *args, election, **kwargs):
        # The election is needed to check the age rule: AddMemberForm(request.POST, election=...)
        super().__init__(*args, **kwargs)
        self.election = election

    def clean_full_name(self):
        # Same tidying as the import: "AMA  MENSAH" -> "Ama Mensah"
        name = clean_name(self.cleaned_data["full_name"])
        # Two names at least, so officials and the parish office can tell people apart
        if len(name.split()) < 2:
            raise forms.ValidationError("Enter their first name and surname.")
        return name

    def clean_date_of_birth(self):
        dob = _check_birth_date(self.cleaned_data["date_of_birth"])
        # The same age rule as everyone on the church list
        earliest, latest = self.election.dob_range()
        if (earliest and dob < earliest) or (latest and dob > latest):
            age = age_on(dob, self.election.date)
            raise forms.ValidationError(
                f"They'll be {age} on election day: outside the age rule "
                f"({self.election.age_rule}), so they can't vote in this election."
            )
        return dob

    def clean_phone(self):
        raw = self.cleaned_data["phone"].strip()
        if not raw:
            return ""
        # Same cleaning as the import: "+233 24 123 4567" -> "0241234567"
        numbers = clean_phones(raw)
        if not numbers:
            raise forms.ValidationError(
                "That doesn't look like a phone number. Check it, or leave it empty."
            )
        # One number is enough here
        return numbers[0]

    def clean_community(self):
        community = self.cleaned_data["community"]
        return clean_name(community) if community else ""