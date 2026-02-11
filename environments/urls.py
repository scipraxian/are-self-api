from django.urls import path

from .views import SelectEnvironmentView

app_name = 'environments'

urlpatterns = [
    path(
        'select/<uuid:pk>/',
        SelectEnvironmentView.as_view(),
        name='select_environment',
    ),
]
