from django.urls import path

from . import views

app_name = "batteries"

urlpatterns = [
    path("", views.BatteryListView.as_view(), name="list"),
    path("new/", views.BatteryCreateView.as_view(), name="create"),
    path("<uuid:public_id>/", views.BatteryDetailView.as_view(), name="detail"),
    path("<uuid:public_id>/edit/", views.BatteryUpdateView.as_view(), name="edit"),
    path("<uuid:public_id>/archive/", views.BatteryArchiveView.as_view(), name="archive"),
]
