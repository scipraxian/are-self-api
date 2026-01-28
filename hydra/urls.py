# C:\talos\hydra\urls.py refactored for consistency
from django.urls import path

from .hydra_graph import HydraGraphAPI
from .views import (
    BattleStationStreamView,
    HeadLogDetailView,
    HydraControlsView,
    HydraGraphEditorView,
    LaunchSpellbookView,
    SpawnMonitorDetailView,
    SpawnTerminateView,
)

urlpatterns = [
    path(
        'launch/<uuid:spellbook_id>/',
        LaunchSpellbookView.as_view(),
        name='hydra_launch',
    ),
    path(
        'monitor/<uuid:pk>/',
        SpawnMonitorDetailView.as_view(),
        name='hydra_spawn_monitor',
    ),
    path(
        'logs/<uuid:pk>/', HeadLogDetailView.as_view(), name='hydra_head_logs'
    ),
    path(
        'battle-stream/<uuid:pk>/',
        BattleStationStreamView.as_view(),
        name='hydra_battle_stream',
    ),
    path(
        'terminate/<uuid:pk>/',
        SpawnTerminateView.as_view(),
        name='hydra_spawn_terminate',
    ),
    path('controls/', HydraControlsView.as_view(), name='hydra_controls'),
    path(
        'editor/<str:book_id>/',
        HydraGraphEditorView.as_view(),
        name='graph_editor',
    ),
    path(
        'graph/<str:book_id>/<str:action>',
        HydraGraphAPI.as_view(),
        name='graph_api_action',
    ),
    path(
        'graph/<str:book_id>/', HydraGraphAPI.as_view(), name='graph_api_root'
    ),
]
