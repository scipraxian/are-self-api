from rest_framework import viewsets

from central_nervous_system.models import NeuralPathway
from central_nervous_system.serializers.v2_serializers import (
    Neural3DLayoutSerializer,
)


class Pathway3DViewSet(viewsets.ReadOnlyModelViewSet):
    """
    V2 Endpoint specifically formatted for the Are-Self 3D frontend.
    """

    queryset = NeuralPathway.objects.all().order_by('name')
    serializer_class = Neural3DLayoutSerializer
