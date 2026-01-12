from django.urls import path

from .views import CortexLaunchView, CortexSessionView, CortexStreamPartialView, CortexTickActionView

app_name = 'talos_reasoning'

urlpatterns = [
    path('cortex/<uuid:session_id>/',
         CortexSessionView.as_view(),
         name='cortex_view'),
    path('cortex/<uuid:session_id>/stream/',
         CortexStreamPartialView.as_view(),
         name='cortex_stream'),
    path('cortex/<uuid:session_id>/tick/',
         CortexTickActionView.as_view(),
         name='cortex_tick'),
    path('launch/', CortexLaunchView.as_view(), name='cortex_launch'),
]
