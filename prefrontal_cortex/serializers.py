import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework import serializers

from common.constants import ALL_FIELDS
from environments.serializers import ProjectEnvironmentSerializer
from frontal_lobe.serializers import TalosEngramSerializer
from identity.serializers import IdentityDiscSerializer

from .models import (
    PFCComment,
    PFCEpic,
    PFCItemStatus,
    PFCStory,
    PFCTag,
    PFCTask,
)

User = get_user_model()


@dataclass
class PFCActionResponse:
    action: str
    item_type: str
    item_id: UUID
    data: Any
    ok: bool = True
    error: Optional[str] = None


class PFCActionResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    action = serializers.CharField()
    item_type = serializers.CharField()
    item_id = serializers.UUIDField()
    data = serializers.JSONField(required=False)
    error = serializers.CharField(required=False, allow_blank=True)


class TicketAction(str, Enum):
    CREATE = 'create'
    UPDATE = 'update'
    SEARCH = 'search'
    COMMENT = 'comment'
    READ = 'read'

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


def make_action_response(
    *,
    action: TicketAction,
    item_type: str = '',
    item_id: Optional[UUID] = None,
    data: Any = None,
    ok: bool = True,
    error: Optional[str] = None,
) -> str:
    """
    Helper to build a PFCActionResponse and serialize it to JSON.
    This centralizes JSON + serializer usage so call sites stay clean.
    """
    obj = PFCActionResponse(
        action=str(action),
        item_type=item_type,
        item_id=item_id or UUID(int=0),
        data=data if data is not None else {},
        ok=ok,
        error=error,
    )
    # Use DjangoJSONEncoder so UUIDs and other Django types are safe.
    return json.dumps(
        PFCActionResponseSerializer(instance=obj).data,
        cls=DjangoJSONEncoder,
    )


class UserLightweightSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class PFCItemStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = PFCItemStatus
        fields = ALL_FIELDS


class PFCTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PFCTag
        fields = ALL_FIELDS


class PFCEpicSerializer(serializers.ModelSerializer):
    class Meta:
        model = PFCEpic
        fields = ALL_FIELDS


class PFCStorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PFCStory
        fields = ALL_FIELDS


class PFCTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PFCTask
        fields = ALL_FIELDS


class PFCCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PFCComment
        fields = ALL_FIELDS


class PFCEpicDetailSerializer(serializers.ModelSerializer):
    status = PFCItemStatusSerializer(read_only=True)
    environment = ProjectEnvironmentSerializer(read_only=True)
    tags = PFCTagSerializer(many=True, read_only=True)
    source_engrams = TalosEngramSerializer(many=True, read_only=True)
    owning_disc = IdentityDiscSerializer(read_only=True)
    previous_owners = IdentityDiscSerializer(many=True, read_only=True)
    comments = serializers.SerializerMethodField()

    class Meta:
        model = PFCEpic
        fields = ALL_FIELDS

    def get_comments(self, obj):
        return PFCCommentDetailSerializer(
            obj.comments.all().order_by('created'), many=True
        ).data


class PFCStoryDetailSerializer(serializers.ModelSerializer):
    epic = PFCEpicSerializer(read_only=True)
    status = PFCItemStatusSerializer(read_only=True)
    tags = PFCTagSerializer(many=True, read_only=True)
    source_engrams = TalosEngramSerializer(many=True, read_only=True)
    owning_disc = IdentityDiscSerializer(read_only=True)
    previous_owners = IdentityDiscSerializer(many=True, read_only=True)
    comments = serializers.SerializerMethodField()

    class Meta:
        model = PFCStory
        fields = ALL_FIELDS

    def get_comments(self, obj):
        return PFCCommentDetailSerializer(
            obj.comments.all().order_by('created'), many=True
        ).data


class PFCTaskDetailSerializer(serializers.ModelSerializer):
    story = PFCStorySerializer(read_only=True)
    status = PFCItemStatusSerializer(read_only=True)
    tags = PFCTagSerializer(many=True, read_only=True)
    previous_owners = IdentityDiscSerializer(many=True, read_only=True)

    class Meta:
        model = PFCTask
        fields = ALL_FIELDS


class PFCCommentDetailSerializer(serializers.ModelSerializer):
    user = UserLightweightSerializer(read_only=True)
    tags = PFCTagSerializer(many=True, read_only=True)
    epic = PFCEpicSerializer(read_only=True)
    story = PFCStorySerializer(read_only=True)
    task = PFCTaskSerializer(read_only=True)

    class Meta:
        model = PFCComment
        fields = ALL_FIELDS
