'''URL configuration for the dashboard application.'''

from django.urls import path, include

from dashboard.views import AgentListView, NeuralStatusView
from dashboard.views import BuildStatusView
from dashboard.views import DashboardHomeView
from dashboard.views import DeleteAgentView
from dashboard.views import ScanNetworkView
from dashboard.views import ShutdownView
from dashboard.views import TriggerBuildView

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='home'),
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
    path('neural-status/', NeuralStatusView.as_view(), name='neural_status')
]
