from django.urls import path
from . import views

urlpatterns = [
    path('campaign-section/', views.dashboard_campaign_section, name='dashboard_campaign_section'),
    path('launch/', views.launch_pipeline, name='launch_pipeline'),
    path('monitor/<int:run_id>/', views.pipeline_live_monitor, name='pipeline_live_monitor'),
    path('step-logs/<int:step_id>/', views.pipeline_live_logs_partial, name='pipeline_step_logs'),
    path('reset-campaign/', views.reset_campaign_view, name='reset_campaign'),
]
