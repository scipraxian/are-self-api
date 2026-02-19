from django.urls import path

from . import api

app_name = 'talos_reasoning'

urlpatterns = [
    path(
        'interface/<uuid:session_id>/',
        api.reasoning_interface,
        name='reasoning_interface',
    ),
    path('lcars/<uuid:session_id>/', api.lcars_view, name='lcars_view'),
    path(
        'api/graph/<uuid:session_id>/',
        api.session_graph_data_api,
        name='session_graph_data',
    ),
]
