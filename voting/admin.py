"""
Admin pages for you and the Commissioner (at /admin/).
Setting up a new election happens entirely here: no code changes.
"""
from django.contrib import admin
from django.db.models import DateField, Value
from django.utils import timezone

from .models import (
    Election,
    Member,
    OrganizerProfile,
    PollingCentre,
    TickUndo,
    VoteCheckIn,
    VotingSession,
)


class VotingSessionInline(admin.TabularInline):
    # Sessions are edited inside their election's page, as rows in a table
    model = VotingSession
    fields = ("centre", "label", "starts_at")
    extra = 1


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "age_rule", "is_active")
    inlines = [VotingSessionInline]


@admin.register(PollingCentre)
class PollingCentreAdmin(admin.ModelAdmin):
    list_display = ("name",)


class SourceFilter(admin.SimpleListFilter):
    """Filter on the right of the member list: from the church list, or added on the day."""
    title = "where from"
    parameter_name = "source"

    def lookups(self, request, model_admin):
        return [("church", "Church list"), ("added", "Added by an official")]

    def queryset(self, request, queryset):
        if self.value() == "church":
            return queryset.filter(added_at__isnull=True)
        if self.value() == "added":
            return queryset.filter(added_at__isnull=False)
        return queryset


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    # Columns shown in the member list
    list_display = ("full_name", "church_id", "date_of_birth", "age", "community", "source")
    # Search covers every phone number, not just the first one
    search_fields = ("full_name", "church_id", "phone", "other_phones")
    # "Date of birth: Empty" lists everyone the Needs checking page is about;
    # "Added by an official" lists everyone added because they weren't on the church list
    list_filter = (SourceFilter, ("date_of_birth", admin.EmptyFieldListFilter), "community")
    # Set only by the app (Needs checking page, or an official adding someone),
    # so they can be read here but not typed in
    readonly_fields = (
        "dob_added_by", "dob_added_at",
        "added_by", "added_at", "added_centre", "matches_when_added",
    )

    def get_queryset(self, request):
        # Look up the active election ONCE per page, and attach its date to every row,
        # so the age column doesn't run one extra query per member
        election = Election.objects.active()
        day = election.date if election else timezone.localdate()
        return super().get_queryset(request).annotate(
            age_date=Value(day, output_field=DateField())
        )

    @admin.display(description="Age on election day")
    def age(self, obj):
        return obj.age_on(obj.age_date)

    @admin.display(description="Where from")
    def source(self, obj):
        return "Added by an official" if obj.is_added_on_the_day else "Church list"


@admin.register(OrganizerProfile)
class OrganizerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "centre")
    list_filter = ("centre",)


@admin.register(VoteCheckIn)
class VoteCheckInAdmin(admin.ModelAdmin):
    list_display = ("member", "election", "session", "ticked_by", "ticked_at")
    list_filter = ("election", "session__centre")
    search_fields = ("member__full_name",)

    # Ticks can only be made from the check-in page, and undone later from the
    # Commissioner's undo page (which keeps a log). So the admin is view-only here.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TickUndo)
class TickUndoAdmin(admin.ModelAdmin):
    list_display = ("member", "election", "ticked_at", "ticked_by", "undone_at", "undone_by")
    list_filter = ("election",)
    search_fields = ("member__full_name", "reason")

    # The undo log is a permanent record: it can be read here, never added to,
    # changed or deleted. New entries come only from the Commissioner's undo page.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False