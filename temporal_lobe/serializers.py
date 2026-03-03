from rest_framework import serializers

from common.constants import ALL_FIELDS
from identity.models import IdentityDisc
from temporal_lobe.models import IterationShift


class IdentityDiscLightSerializer(serializers.ModelSerializer):
    """Lightweight representation of an Identity Disc for the Inspector."""

    identity_name = serializers.CharField(
        source='identity.name', read_only=True
    )

    class Meta:
        model = IdentityDisc
        fields = ALL_FIELDS


class IterationShiftDetailSerializer(serializers.ModelSerializer):
    """The full state payload for the right-hand panel when a node is clicked."""

    shift_name = serializers.CharField(source='shift.name', read_only=True)
    turn_limit = serializers.IntegerField(
        source='definition.turn_limit', read_only=True
    )
    order = serializers.IntegerField(source='definition.order', read_only=True)
    iteration_name = serializers.CharField(
        source='shift_iteration.name', read_only=True
    )
    participants = serializers.SerializerMethodField()

    class Meta:
        model = IterationShift
        fields = ALL_FIELDS

    def get_participants(self, obj):
        parts = obj.iterationshiftparticipant_set.select_related(
            'iteration_participant', 'iteration_participant__identity'
        ).all()
        discs = [p.iteration_participant for p in parts]
        return IdentityDiscLightSerializer(discs, many=True).data
