import json

from rest_framework import serializers

from central_nervous_system.models import NeuralPathway
from common.constants import ALL_FIELDS


class Neural3DLayoutSerializer(serializers.ModelSerializer):
    """Projects the NeuralPathway into 3D space for the React frontend."""

    nodes = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()

    class Meta:
        model = NeuralPathway
        fields = ALL_FIELDS

    def get_nodes(self, obj):
        neurons = obj.neurons.select_related(
            'effector', 'invoked_pathway', 'distribution_mode'
        ).all()

        node_data = []
        for n in neurons:
            try:
                ui_config = json.loads(n.ui_json)
            except (TypeError, ValueError):
                ui_config = {'x': 0, 'y': 0, 'z': 0}

            node_data.append(
                {
                    'id': str(n.id),
                    'name': n.effector.name if n.effector else 'Sub-Graph',
                    'group': n.effector.distribution_mode.name
                    if n.effector
                    else 'Delegated',
                    'status': getattr(n, 'runtime_status', 'idle'),
                    'fx': ui_config.get('x', None),
                    'fy': ui_config.get('y', None),
                    'fz': ui_config.get('z', None),
                    'is_root': n.is_root,
                }
            )
        return node_data

    def get_links(self, obj):
        axons = obj.axons.all()
        return [
            {
                'source': str(axon.source_id),
                'target': str(axon.target_id),
                'type': axon.type.name.lower(),
            }
            for axon in axons
        ]
