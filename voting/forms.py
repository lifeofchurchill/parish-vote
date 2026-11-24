"""
Forms for the parish election pages.
"""
from django import forms
from django.utils import timezone


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
        dob = self.cleaned_data["date_of_birth"]
        if dob > timezone.localdate():
            raise forms.ValidationError("That date is in the future.")
        if dob.year < 1900:
            raise forms.ValidationError("That date is too far back. Check the year.")
        return dob