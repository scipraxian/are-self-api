from django.urls import path

from central_nervous_system.cns_graph import CNSGraphAPI, CNSGraphLaunchAPI
from central_nervous_system.views.views import SpikeTrainDownloadView

app_name = 'central_nervous_system'

urlpatterns = [
    # Graph API endpoints
    path(
        'graph/<str:pathway_id>/launch/',
        CNSGraphLaunchAPI.as_view(),
        name='graph_launch_api',
    ),
    path(
        'graph/<str:pathway_id>/', CNSGraphAPI.as_view(), name='graph_api_root'
    ),
    path(
        'graph/<str:pathway_id>/<str:action>',
        CNSGraphAPI.as_view(),
        name='graph_api_action',
    ),
    # Download
    path(
        'spike_train/<uuid:pk>/download/',
        SpikeTrainDownloadView.as_view(),
        name='cns_spawn_download',
    ),
]
