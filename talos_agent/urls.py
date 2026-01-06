'''URL configuration for the Talos Agent application.'''

from django.urls import path
from . import views

urlpatterns = [
    path('<uuid:pk>/', views.AgentDetailView.as_view(), name='agent_detail'),
    path('<uuid:pk>/metrics/', views.agent_live_metrics_partial, name='agent_metrics'),
    path('<uuid:pk>/launch/', views.agent_launch_view, name='agent_launch'),
    path('<uuid:pk>/kill/', views.agent_kill_view, name='agent_kill'),
    path('<uuid:pk>/logs/', views.agent_logs_view, name='agent_logs'),
    path('<uuid:pk>/log-feed/', views.agent_log_feed_view, name='agent_log_feed'),
    path('<uuid:pk>/update/', views.agent_update_view, name='agent_update'),
]
