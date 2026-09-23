from django.urls import path

from . import views

app_name = "configurations"

urlpatterns = [
    path("", views.ConfigurationListView.as_view(), name="list"),
    path("new/", views.ConfigurationCreateView.as_view(), name="create"),
    path("<uuid:public_id>/", views.ConfigurationDetailView.as_view(), name="detail"),
    path("<uuid:public_id>/edit/", views.ConfigurationUpdateView.as_view(), name="edit"),
    path("<uuid:public_id>/archive/", views.ConfigurationArchiveView.as_view(), name="archive"),
    path(
        "<uuid:public_id>/versions/new/",
        views.ConfigurationVersionCreateView.as_view(),
        name="version-create",
    ),
    path(
        "versions/<uuid:public_id>/",
        views.ConfigurationVersionDetailView.as_view(),
        name="version-detail",
    ),
    path(
        "versions/<uuid:public_id>/publish/",
        views.ConfigurationVersionPublishView.as_view(),
        name="version-publish",
    ),
    path(
        "versions/<uuid:public_id>/channels/new/",
        views.ChannelSnapshotCreateView.as_view(),
        name="channel-create",
    ),
    path(
        "versions/<uuid:public_id>/channels/<int:channel_id>/edit/",
        views.ChannelSnapshotUpdateView.as_view(),
        name="channel-edit",
    ),
    path(
        "versions/<uuid:public_id>/channels/<int:channel_id>/delete/",
        views.ChannelSnapshotDeleteView.as_view(),
        name="channel-delete",
    ),
    path(
        "versions/<uuid:public_id>/attachments/upload/",
        views.VersionAttachmentUploadView.as_view(),
        name="attachment-upload",
    ),
    path(
        "versions/<uuid:public_id>/attachments/<int:attachment_id>/download/",
        views.VersionAttachmentDownloadView.as_view(),
        name="attachment-download",
    ),
    path(
        "versions/compare/<uuid:from_id>/<uuid:to_id>/",
        views.VersionCompareView.as_view(),
        name="version-compare",
    ),
]
