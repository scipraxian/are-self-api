from .views import LaunchFastValidateView
from django.urls import path

urlpatterns = [
    path('launch/fast-validate/', LaunchFastValidateView.as_view(), name='hydra_launch_fast_validate'),
]