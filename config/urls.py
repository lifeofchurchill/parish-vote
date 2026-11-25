"""
Top-level URLs: the admin, sign-in/sign-out, a health check, and the check-in pages.
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import include, path


def healthz(request):
    """
    A tiny page that just says "ok". Render visits it after each deploy to check the new
    version started properly before switching visitors over to it, and an uptime monitor
    visits it every few minutes to email you if the site ever goes down.
    It doesn't touch the database, so it's always quick.
    """
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    # Django's built-in admin (for you and the Commissioner behind the scenes)
    path("admin/", admin.site.urls),
    # Django's built-in login/logout views; they use templates/registration/login.html
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # "Is the site up?" for Render and the uptime monitor
    path("healthz/", healthz, name="healthz"),
    # The check-in pages live at the root of the site (voting/urls.py)
    path("", include("voting.urls")),
]