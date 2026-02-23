"""URL configuration for the dashboard application."""

from django.urls import include, path

from dashboard.views import DashboardHomeView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardHomeView.as_view(), name='home'),
    path('agent-detail/', include('talos_agent.urls')),
]
