from django.urls import path

from . import views

app_name = "radios"

urlpatterns = [
    path("", views.RadioListView.as_view(), name="list"),
    path("new/", views.RadioCreateView.as_view(), name="create"),
    path("<uuid:public_id>/", views.RadioDetailView.as_view(), name="detail"),
    path("<uuid:public_id>/edit/", views.RadioUpdateView.as_view(), name="edit"),
    path("<uuid:public_id>/archive/", views.RadioArchiveView.as_view(), name="archive"),
    path(
        "<uuid:public_id>/battery/assign/",
        views.AssignBatteryView.as_view(),
        name="assign-battery",
    ),
    path(
        "<uuid:public_id>/battery/unassign/",
        views.UnassignBatteryView.as_view(),
        name="unassign-battery",
    ),
    path(
        "<uuid:public_id>/maintenance/",
        views.MaintenanceEventCreateView.as_view(),
        name="maintenance-create",
    ),
]
