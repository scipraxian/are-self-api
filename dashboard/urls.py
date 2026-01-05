'''URL configuration for the dashboard application.'''

from django.urls import path

from dashboard.views import BuildStatusView
from dashboard.views import DashboardHomeView
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
]
