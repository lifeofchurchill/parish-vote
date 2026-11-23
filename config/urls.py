"""
Top-level URLs: the admin and login/logout.
(The check-in pages get added here in Step 8.)
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    # Django's built-in admin (for you and the Commissioner behind the scenes)
    path("admin/", admin.site.urls),
    # Django's built-in login/logout views; they use templates/registration/login.html
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]