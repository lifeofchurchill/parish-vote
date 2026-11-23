"""
URLs for the check-in pages used by election officials.
"""
from django.urls import path

from . import views

# Namespace: refer to these as "voting:checkin", "voting:set_session", etc.
app_name = "voting"

urlpatterns = [
    # Main page: session picker now; search and results come in the next steps
    path("", views.checkin, name="checkin"),
    # Choose or change the session (which Mass)
    path("session/", views.set_session, name="set_session"),
]