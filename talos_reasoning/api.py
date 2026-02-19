from dataclasses import asdict

from django.shortcuts import render
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import constants, serializers
from .models import ReasoningSession, ReasoningStatus, ReasoningStatusID
from .serializers import CortexContextDTO


class ReasoningSessionViewSet(viewsets.ModelViewSet):
    """
    Command Center for Talos AGI Reasoning Sessions.
    """

    queryset = ReasoningSession.objects.all().order_by('-created')
    serializer_class = serializers.ReasoningSessionSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    search_fields = ['goal']
    filterset_fields = ['status']

    @action(detail=True, methods=['get'])
    def interface(self, request, pk=None):
        """The Standalone Cortex 'Situation Room'."""
        session = self.get_object()

        # 1. Build the strongly-typed DTO
        context_dto = CortexContextDTO(
            session=session,
            goals=session.goals.all().order_by('created'),
            turns=session.turns.all()
            .prefetch_related('tool_calls', 'tool_calls__tool')
            .order_by('turn_number'),
            engrams=session.engram.filter(is_active=True).order_by(
                '-relevance_score', '-created'
            ),
            is_active=session.status_id
            in [ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING],
        )

        # 2. Unpack safely into the render function
        if (
            request.headers.get('HX-Request')
            and request.GET.get('partial') == 'stream'
        ):
            return render(
                request,
                'talos_reasoning/partials/cortex_stream_partial.html',
                asdict(context_dto),  # <-- Clean, typed unpacking
            )

        return render(
            request,
            'talos_reasoning/talos_reasoning_window.html',
            asdict(context_dto),  # <-- Clean, typed unpacking
        )

    @action(detail=True, methods=['get'])
    def lcars(self, request, pk=None):
        """Renders the futuristic LCARS interface wrapper."""
        session = self.get_object()
        return render(
            request, 'talos_reasoning/lcars_view.html', {'session': session}
        )

    @action(detail=True, methods=['get'], url_path='graph_data')
    def graph_data(self, request, pk=None):
        """Returns fully resolved, DTO-bound JSON for the D3 visualization."""
        session = self.get_object()

        turns = list(
            session.turns.all()
            .order_by('turn_number')
            .prefetch_related('tool_calls', 'tool_calls__tool')
        )
        engrams = session.engram.all()

        nodes = []
        links = []
        tool_map = {}

        valid_node_ids = set()

        # 1. Process Turns
        for i, turn in enumerate(turns):
            node_id = f'{constants.NODE_TURN}-{turn.id}'
            valid_node_ids.add(node_id)

            # Format Times safely
            delta_str = (
                f'{turn.delta.total_seconds():.1f}s' if turn.delta else '0s'
            )
            inf_str = (
                f'{turn.inference_time.total_seconds():.1f}s'
                if turn.inference_time
                else '0s'
            )

            nodes.append(
                serializers.GraphNodeDTO(
                    id=node_id,
                    type=constants.NODE_TURN,
                    label=f'Turn {turn.turn_number}',
                    turn_number=turn.turn_number,
                    status=turn.status.name,
                    thought_process=turn.thought_process,
                    request_payload=turn.request_payload,
                    tokens_input=turn.tokens_input,
                    tokens_output=turn.tokens_output,
                    inference_time=inf_str,
                    created=turn.created.isoformat(),
                    delta=delta_str,
                )
            )

            if i > 0:
                prev_turn = turns[i - 1]
                links.append(
                    serializers.GraphLinkDTO(
                        source=f'{constants.NODE_TURN}-{prev_turn.id}',
                        target=node_id,
                        type=constants.LINK_SEQUENCE,
                    )
                )

            # Process Tool Calls
            for call in turn.tool_calls.all():
                tool_name = call.tool.name
                tool_node_id = f'{constants.NODE_TOOL}-{tool_name}'

                if tool_name not in tool_map:
                    tool_map[tool_name] = tool_node_id
                    valid_node_ids.add(tool_node_id)  # Register Node
                    nodes.append(
                        serializers.GraphNodeDTO(
                            id=tool_node_id,
                            type=constants.NODE_TOOL,
                            label=tool_name,
                            is_async=call.tool.is_async,
                        )
                    )

                links.append(
                    serializers.GraphLinkDTO(
                        source=node_id,
                        target=tool_node_id,
                        type=constants.LINK_USES_TOOL,
                        call_id=call.call_id,
                        arguments=call.arguments,
                        result=call.result_payload or '',
                        traceback=call.traceback or '',
                    )
                )

        # 2. Process Engrams
        for engram in engrams:
            node_id = f'{constants.NODE_ENGRAM}-{engram.id}'
            valid_node_ids.add(node_id)  # Register Node

            nodes.append(
                serializers.GraphNodeDTO(
                    id=node_id,
                    type=constants.NODE_ENGRAM,
                    label=f'Engram #{engram.id}',
                    description=engram.description,
                    relevance=engram.relevance_score,
                    is_active=engram.is_active,
                )
            )

            for turn in engram.source_turns.all():
                turn_node_id = f'{constants.NODE_TURN}-{turn.id}'

                # --- FIX: Only link if the Turn exists in THIS specific graph ---
                if turn_node_id in valid_node_ids:
                    links.append(
                        serializers.GraphLinkDTO(
                            source=turn_node_id,
                            target=node_id,
                            type=constants.LINK_CREATED_IN,
                        )
                    )

        session_data = serializers.ReasoningSessionSerializer(session).data
        dto_payload = serializers.SessionGraphDTO(
            session=session_data, nodes=nodes, links=links
        )
        response_serializer = serializers.SessionGraphDataSerializer(
            dto_payload
        )

        return Response(response_serializer.data)
