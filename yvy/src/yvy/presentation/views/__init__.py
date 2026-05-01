"""Views (pantallas) de la aplicación YVY."""

from yvy.presentation.views.dashboard_admin import DashboardAdminView
from yvy.presentation.views.login_view import LoginView
from yvy.presentation.views.sync_status_view import SyncStatusView

__all__ = [
    "DashboardAdminView",
    "LoginView",
    "SyncStatusView",
]
