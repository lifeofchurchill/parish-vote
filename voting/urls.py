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
    # Find a ticked voter, and the undo log
    path("commissioner/undo/", commissioner_views.undo_search, name="undo"),
    # Confirm screen (GET) and the actual undo (POST) for one tick
    path("commissioner/undo/<int:checkin_id>/", commissioner_views.undo_tick, name="undo_tick"),
]