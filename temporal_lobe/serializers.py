from rest_framework import serializers

from common.constants import ALL_FIELDS
from identity.models import Identity, IdentityDisc
from temporal_lobe.models import (
    Iteration,
    IterationDefinition,
    IterationShift,
    IterationShiftDefinition,
    IterationShiftDefinitionParticipant,
    IterationShiftParticipant,
    IterationStatus,
    Shift,
    ShiftDefaultParticipant,
)


class IdentityDiscLightSerializer(serializers.ModelSerializer):
    """Lightweight representation of an Identity Disc for the Inspector."""

    class Meta:
        model = IdentityDisc
        fields = ALL_FIELDS


class IdentityLightSerializer(serializers.ModelSerializer):
    """Lightweight representation of a base Identity for definition participants."""

    class Meta:
        model = Identity
        fields = ['id', 'name']


class ShiftSerializer(serializers.ModelSerializer):
    """Serializer for the Shift model."""

    class Meta:
        model = Shift
        fields = ALL_FIELDS


class ShiftDefaultParticipantSerializer(serializers.ModelSerializer):
    """Serializer for the ShiftDefaultParticipant model."""

    class Meta:
        model = ShiftDefaultParticipant
        fields = ALL_FIELDS


class ShiftDefaultParticipantSerializer(serializers.ModelSerializer):
    """Serializer for the ShiftDefaultParticipant model."""

    class Meta:
        model = ShiftDefaultParticipant
        fields = ALL_FIELDS


class IterationShiftDefinitionParticipantSerializer(
    serializers.ModelSerializer
):
    """Serializer for the IterationShiftDefinitionParticipant model."""

    participant_detail = IdentityDiscLightSerializer(
        source='identity_disc', read_only=True
    )

    class Meta:
        model = IterationShiftDefinitionParticipant
        fields = [
            'id',
            'shift_definition',
            'identity_disc',
            'participant_detail',
        ]


class IterationShiftDefinitionSerializer(serializers.ModelSerializer):
    """Serializer for the IterationShiftDefinition model."""

    shift = ShiftSerializer(read_only=True)

    participants = IterationShiftDefinitionParticipantSerializer(
        source='iterationshiftdefinitionparticipant_set',
        many=True,
        read_only=True,
    )

    class Meta:
        model = IterationShiftDefinition
        fields = ALL_FIELDS


class IterationDefinitionSerializer(serializers.ModelSerializer):
    """Serializer for the IterationDefinition model."""

    shift_definitions = IterationShiftDefinitionSerializer(
        source='iterationshiftdefinition_set',
        many=True,
        read_only=True,
    )

    class Meta:
        model = IterationDefinition
        fields = ALL_FIELDS


class IterationStatusSerializer(serializers.ModelSerializer):
    """Serializer for the IterationStatus model."""

    class Meta:
        model = IterationStatus
        fields = ALL_FIELDS


class IterationShiftParticipantSerializer(serializers.ModelSerializer):
    disc = IdentityDiscLightSerializer(
        source='iteration_participant', read_only=True
    )

    class Meta:
        model = IterationShiftParticipant
        fields = ALL_FIELDS


class IterationShiftDetailSerializer(serializers.ModelSerializer):
    """The full state payload for a single column/shift."""

    name = serializers.CharField(source='shift.name', read_only=True)
    turn_limit = serializers.IntegerField(
        source='definition.turn_limit', read_only=True
    )
    participants = IterationShiftParticipantSerializer(
        source='iterationshiftparticipant_set', many=True, read_only=True
    )

    class Meta:
        model = IterationShift
        fields = ALL_FIELDS


class IterationSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    definition_name = serializers.CharField(
        source='definition.name', read_only=True
    )
    shifts = IterationShiftDetailSerializer(
        source='iterationshift_set', many=True, read_only=True
    )

    class Meta:
        model = Iteration
        fields = ALL_FIELDS
