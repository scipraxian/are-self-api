from django.urls import path
from .views import LaunchSpellbookView

urlpatterns = [
    path('launch/<uuid:spellbook_id>/', LaunchSpellbookView.as_view(), name='hydra_launch'),
]