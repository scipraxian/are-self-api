from django.urls import path
from .views import ChatOverrideView

app_name = 'talos_frontal'

urlpatterns = [
    path('chat/', ChatOverrideView.as_view(), name='chat_override'),
]
