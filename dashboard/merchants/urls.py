from django.contrib.auth import views as auth_views
from django.urls import path

from merchants import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="merchants/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("transactions/", views.transactions_view, name="transactions"),
    path("api-keys/", views.api_keys_view, name="api_keys"),
    path("webhooks/", views.webhooks_view, name="webhooks"),
    path("admin-overview/", views.admin_overview, name="admin_overview"),
]
