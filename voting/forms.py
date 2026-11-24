"""
Forms for the parish election pages.
"""
from django import forms


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