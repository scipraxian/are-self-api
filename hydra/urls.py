from django.urls import path

from . import views
from .hydra_graph import HydraGraphAPI, HydraGraphLaunchAPI

app_name = 'hydra'

urlpatterns = [
    # --- The Graph App ---
    path(
        'graph/editor/<str:book_id>/',
        views.HydraGraphEditorView.as_view(),
        name='graph_editor',
    ),
    path(
        'graph/spawn/<uuid:spawn_id>/',
        views.HydraGraphMonitorView.as_view(),
        name='graph_monitor',
    ),
    # API endpoints
    path(
        'graph/<str:book_id>/launch/',
        HydraGraphLaunchAPI.as_view(),
        name='graph_launch_api',
    ),
    path(
        'graph/<str:book_id>/', HydraGraphAPI.as_view(), name='graph_api_root'
    ),
    path(
        'graph/<str:book_id>/<str:action>',
        HydraGraphAPI.as_view(),
        name='graph_api_action',
    ),
    # --- The War Room ---
    path(
        'head/<uuid:pk>/', views.HeadLogDetailView.as_view(), name='head_detail'
    ),
    # --- Actions ---
    path(
        'launch/<uuid:spellbook_id>/',
        views.LaunchSpellbookView.as_view(),
        name='hydra_launch',
    ),
    path(
        'spawn/<uuid:pk>/terminate/',
        views.TerminateSpawnView.as_view(),
        name='hydra_spawn_terminate',
    ),
    path(
        'spawn/<uuid:pk>/stop/',
        views.GracefulStopSpawnView.as_view(),
        name='hydra_spawn_stop_graceful',
    ),
    # --- LEGACY COMPATIBILITY ---
    path(
        'head/<uuid:pk>/logs/',
        views.HeadLogDetailView.as_view(),
        name='hydra_head_logs',
    ),
    path(
        'monitor/<uuid:spawn_id>/',
        views.HydraGraphMonitorView.as_view(),
        name='hydra_spawn_monitor',
    ),
    path(
        'monitor/partial/<uuid:pk>/',
        views.SpawnMonitorDetailView.as_view(),
        name='hydra_spawn_monitor_partial',
    ),
    # Misc
    path('controls/', views.HydraControlsView.as_view(), name='hydra_controls'),
    path(
        'battle/<uuid:spawn_id>/',
        views.HydraBattleStationView.as_view(),
        name='hydra_battle_station',
    ),
    path(
        'battle/stream/<uuid:spawn_id>/',
        views.HydraBattleStreamView.as_view(),
        name='hydra_battle_stream',
    ),
]
