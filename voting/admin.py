"""
Admin pages for you and the Commissioner (at /admin/).
"""
from django.contrib import admin

from .models import Member, OrganizerProfile, VoteCheckIn


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    # Columns shown in the member list
    list_display = ("full_name", "church_id", "date_of_birth", "age", "community")
    # Search covers every phone number, not just the first one
    search_fields = ("full_name", "church_id", "phone", "other_phones")
    list_filter = ("community",)


@admin.register(OrganizerProfile)
class OrganizerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "centre")
    list_filter = ("centre",)


@admin.register(VoteCheckIn)
class VoteCheckInAdmin(admin.ModelAdmin):
    list_display = ("member", "centre", "session", "ticked_by", "ticked_at")
    list_filter = ("centre", "session")
    search_fields = ("member__full_name",)

    # Ticks can only be made from the check-in page, and undone later from the
    # Commissioner's undo page (which keeps a log). So the admin is view-only here.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False