from django.urls import path

from . import views
from .cns_graph import CNSGraphAPI, CNSGraphLaunchAPI

app_name = 'central_nervous_system'

urlpatterns = [
    # --- The Graph App ---
    path(
        'graph/editor/<str:book_id>/',
        views.CNSGraphEditorView.as_view(),
        name='graph_editor',
    ),
    path(
        'graph/spike_train/<uuid:spawn_id>/',
        views.CNSGraphMonitorView.as_view(),
        name='graph_monitor',
    ),
    # API endpoints
    path(
        'graph/<str:book_id>/launch/',
        CNSGraphLaunchAPI.as_view(),
        name='graph_launch_api',
    ),
    path('graph/<str:book_id>/', CNSGraphAPI.as_view(),
         name='graph_api_root'),
    path(
        'graph/<str:book_id>/<str:action>',
        CNSGraphAPI.as_view(),
        name='graph_api_action',
    ),
    # --- The War Room ---
    path('spike/<uuid:pk>/',
         views.HeadLogDetailView.as_view(),
         name='head_detail'),
    # --- Actions ---
    path(
        'launch/<uuid:spellbook_id>/',
        views.LaunchNeuralPathwayView.as_view(),
        name='cns_launch',
    ),
    path(
        'book/<uuid:pk>/favorite/',
        views.ToggleFavoriteView.as_view(),
        name='toggle_favorite',
    ),
    path(
        'spike_train/<uuid:pk>/terminate/',
        views.TerminateSpawnView.as_view(),
        name='cns_spawn_terminate',
    ),
    path(
        'spike_train/<uuid:pk>/stop/',
        views.GracefulStopSpawnView.as_view(),
        name='cns_spawn_stop_graceful',
    ),
    # --- LEGACY COMPATIBILITY ---
    path(
        'spike/<uuid:pk>/logs/',
        views.HeadLogDetailView.as_view(),
        name='cns_head_logs',
    ),
    path(
        'monitor/<uuid:spawn_id>/',
        views.CNSGraphMonitorView.as_view(),
        name='cns_spawn_monitor',
    ),
    path(
        'monitor/partial/<uuid:pk>/',
        views.SpawnMonitorDetailView.as_view(),
        name='cns_spawn_monitor_partial',
    ),
    # Misc
    path('controls/', views.CNSControlsView.as_view(), name='cns_controls'),
    path(
        'battle/<uuid:spawn_id>/',
        views.CNSBattleStationView.as_view(),
        name='cns_battle_station',
    ),
    path(
        'battle/stream/<uuid:spawn_id>/',
        views.CNSBattleStreamView.as_view(),
        name='cns_battle_stream',
    ),
    path(
        'spike_train/<uuid:pk>/download/',
        views.SpikeTrainDownloadView.as_view(),
        name='cns_spawn_download',
    ),
]
