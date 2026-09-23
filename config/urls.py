from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from apps.configurations.views import ProgrammingRecordCreateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", RedirectView.as_view(pattern_name="fleets:home"), name="index"),
    path("fleets/", include("apps.fleets.urls")),
    path("fleets/<uuid:fleet_public_id>/radios/", include("apps.radios.urls")),
    path("fleets/<uuid:fleet_public_id>/batteries/", include("apps.radios.battery_urls")),
    path("fleets/<uuid:fleet_public_id>/configurations/", include("apps.configurations.urls")),
    path(
        "fleets/<uuid:fleet_public_id>/radios/<uuid:public_id>/programming/",
        ProgrammingRecordCreateView.as_view(),
        name="programming-create",
    ),
]
