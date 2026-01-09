from django.urls import path
from .views import LaunchSpellbookView, spawn_monitor_view, head_log_view, HydraControlsView

urlpatterns = [
    path('launch/<uuid:spellbook_id>/', LaunchSpellbookView.as_view(), name='hydra_launch'),
    path('monitor/<uuid:spawn_id>/', spawn_monitor_view, name='hydra_spawn_monitor'),
    path('logs/<uuid:head_id>/', head_log_view, name='hydra_head_logs'),
    path('controls/', HydraControlsView.as_view(), name='hydra_controls'),
]