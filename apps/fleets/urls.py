from django.urls import path

from . import views

app_name = "fleets"

urlpatterns = [
    path("", views.home, name="home"),
    path("new/", views.FleetCreateView.as_view(), name="create"),
    path("<uuid:public_id>/", views.FleetDetailView.as_view(), name="detail"),
]
