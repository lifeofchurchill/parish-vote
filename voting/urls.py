"""
URLs for the check-in pages used by election officials.
"""
from django.urls import path

from . import commissioner_views, views

# Namespace: refer to these as "voting:checkin", "voting:tick", etc.
app_name = "voting"

urlpatterns = [
    # Main page: session picker, live panel, search and results
    path("", views.checkin, name="checkin"),
    # Choose or change the session (which Mass)
    path("session/", views.set_session, name="set_session"),
    # Confirm screen (GET) and the actual tick (POST) for one member
    path("tick/<int:member_id>/", views.tick, name="tick"),

    # Electoral Commissioner pages (staff accounts only)
    path("commissioner/", commissioner_views.dashboard, name="dashboard"),
    # Members with no date of birth, and saving one for a member
    path("commissioner/needs-checking/", commissioner_views.needs_checking, name="needs_checking"),
    path("commissioner/needs-checking/<int:member_id>/", commissioner_views.add_date_of_birth, name="add_dob"),
    # Print & download: the page, the paper backup list, and the two CSV files
    path("commissioner/records/", commissioner_views.records, name="records"),
    path("commissioner/records/backup-list/", commissioner_views.backup_list, name="backup_list"),
    path("commissioner/records/who-voted.csv", commissioner_views.download_voted, name="download_voted"),
    path("commissioner/records/undo-log.csv", commissioner_views.download_undo_log, name="download_undo_log"),
    # Find a ticked voter, and the undo log
    path("commissioner/undo/", commissioner_views.undo_search, name="undo"),
    # Confirm screen (GET) and the actual undo (POST) for one tick
    path("commissioner/undo/<int:checkin_id>/", commissioner_views.undo_tick, name="undo_tick"),
]