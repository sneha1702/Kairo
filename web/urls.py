from django.urls import path
from web import views

urlpatterns = [
    path("",                          views.index,                    name="index"),
    path("login/",                    views.login_view,               name="login"),
    path("logout/",                   views.logout_view,              name="logout"),
    path("admin-panel/",              views.admin_panel,              name="admin_panel"),

    # Auth API
    path("api/auth/login/",           views.api_login,                name="api_login"),
    path("api/auth/register/",        views.api_register,             name="api_register"),

    # Profile API
    path("api/profile/save/",         views.api_profile_save,         name="api_profile_save"),
    path("api/profile/change-password/", views.api_password_change,   name="api_password_change"),
    path("api/profile/delete-account/",  views.api_delete_account,    name="api_delete_account"),

    # Admin API
    path("api/admin/run-detection/",  views.api_admin_run_detection,  name="api_admin_run_detection"),
    path("api/admin/run-ingestion/",  views.api_admin_run_ingestion,  name="api_admin_run_ingestion"),
    path("api/admin/purge/",          views.api_admin_purge,          name="api_admin_purge"),
    path("api/admin/backfill/",       views.api_admin_backfill,       name="api_admin_backfill"),
]
