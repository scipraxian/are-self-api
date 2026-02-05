"""URL configuration for the dashboard application."""

from django.urls import include, path

from dashboard.views import (
    AgentListView,
    BuildStatusView,
    DashboardHomeView,
    DeleteAgentView,
    NeuralStatusView,
    ScanNetworkView,
    ShutdownView,
    SwimlanePartialView,
    TriggerBuildView,
)

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='home'),
    path(
        'swimlane/<uuid:pk>/',
        SwimlanePartialView.as_view(),
        name='swimlane_partial',
    ),
    path(
        'trigger-build/',
        TriggerBuildView.as_view(),
        name='trigger_build',
    ),
    path(
        'check-status/<str:task_id>/',
        BuildStatusView.as_view(),
        name='check_build_status',
    ),
    path(
        'scan-network/',
        ScanNetworkView.as_view(),
        name='scan_network',
    ),
    path(
        'agents/',
        AgentListView.as_view(),
        name='agent_list',
    ),
    path(
        'delete-agent/<uuid:pk>/',
        DeleteAgentView.as_view(),
        name='delete_agent',
    ),
    path(
        'shutdown/',
        ShutdownView.as_view(),
        name='shutdown',
    ),
    path('agent-detail/', include('talos_agent.urls')),
    path('neural-status/', NeuralStatusView.as_view(), name='neural_status'),
]
