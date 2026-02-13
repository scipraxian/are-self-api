"""URL configuration for the dashboard application."""

from django.urls import include, path

from dashboard.views import DashboardHomeView, ShutdownView, SwimlanePartialView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='home'),
    path(
        'swimlane/<uuid:pk>/',
        SwimlanePartialView.as_view(),
        name='swimlane_partial',
    ),
    path('agent-detail/', include('talos_agent.urls')),
    path(
        'shutdown/',
        ShutdownView.as_view(),
        name='shutdown',
    ),
]
