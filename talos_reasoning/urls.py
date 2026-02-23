from django.urls import path

from . import views

app_name = 'talos_reasoning'

urlpatterns = [
    path(
        'interface/<uuid:session_id>/',
        views.ReasoningInterfaceView.as_view(),
        name='reasoning_interface',
    ),
    path(
        'lcars/<uuid:session_id>/', views.LcarsView.as_view(), name='lcars_view'
    ),
]
