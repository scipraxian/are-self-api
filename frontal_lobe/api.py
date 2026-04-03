from django.db.models import Count, Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from central_nervous_system.models import SpikeStatus
from central_nervous_system.tasks import fire_spike
from frontal_lobe.models import ReasoningStatusID
from frontal_lobe.serializers import (
    KEY_REPLY,
    ResumeSessionRequestSerializer,
    ResumeSessionResponseDTO,
    ResumeSessionResponseSerializer,
)
from thalamus.serializers import (
    ThalamusMessageListDTO,
    ThalamusMessageListSerializer,
)
from thalamus.thalamus import (
    get_chat_history,
    inject_swarm_chatter,
)

from . import serializers
from .models import ReasoningSession, ReasoningTurn

MSG_REIGNITED = 'Neural pathway re-ignited.'
MSG_INVALID_STATE = (
    'Session is not awaiting attention. Current status: {status_id}'
)


class ReasoningSessionViewSet(viewsets.ModelViewSet):
    """Command Center for Are-Self AGI Reasoning Sessions."""

    serializer_class = serializers.ReasoningSessionLiteSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    search_fields = ['id', 'conclusion__summary']
    filterset_fields = ['status']

    def get_queryset(self):
        qs = ReasoningSession.objects.all().order_by('-modified')
        if self.action == 'list':
            # Lightweight query for list — annotate turns_count, only join status + identity_disc
            qs = qs.select_related('status', 'identity_disc').annotate(
                turns_count=Count('turns')
            )
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return serializers.ReasoningSessionMinimalSerializer
        return serializers.ReasoningSessionLiteSerializer

    @action(detail=True, methods=['get'], url_path='graph_data')
    def graph_data(self, request, pk=None):
        session = (
            self.get_queryset()
            .select_related('status', 'conclusion', 'conclusion__status')
            .prefetch_related(
                Prefetch(
                    'turns',
                    queryset=ReasoningTurn.objects.select_related(
                        'status'
                    ).order_by('turn_number'),
                ),
                'turns__tool_calls__tool',
                'engrams__source_turns',
            )
            .get(pk=pk)
        )
        serializer = serializers.ReasoningSessionGraphSerializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def rerun(self, request, pk=None):
        """Reboots the Cortex by restarting the originating Spike."""
        session = self.get_object()
        spike = session.spike

        if not spike:
            return Response({'error': 'No associated Spike found.'}, status=400)

        spike.status_id = SpikeStatus.PENDING
        spike.save(update_fields=['status'])
        fire_spike.delay(spike.id)

        return Response(
            {
                'status': 'Rebooting',
                'spike_train_id': str(spike.spike_train.id)
                if spike.spike_train
                else None,
            }
        )

    @action(detail=True, methods=['post'])
    def attention_required(self, request, pk=None):
        """The graceful pause trigger."""
        session = self.get_object()
        session.status_id = ReasoningStatusID.ATTENTION_REQUIRED

        # NOTE: saving this triggers the broadcast_session_status signal in Thalamus!
        session.save(update_fields=['status_id'])

        return Response({'status': 'Attention required'})

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """The flat chat pipeline for assistant-ui."""
        session = self.get_object()
        include_volatile = (
            request.query_params.get('volatile', 'false').lower() == 'true'
        )

        messages_payload = get_chat_history(
            session, include_volatile=include_volatile
        )
        response_dto = ThalamusMessageListDTO(messages=messages_payload)

        return Response(
            ThalamusMessageListSerializer(instance=response_dto).data
        )

    @action(
        detail=True,
        methods=['post'],
        serializer_class=ResumeSessionRequestSerializer,
    )
    def resume(self, request, pk=None):
        """Injects human chatter into a ReasoningSession and ensures it is awake."""
        session = self.get_object()

        request_serializer = self.get_serializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        user_reply = request_serializer.validated_data.get(KEY_REPLY, '')

        # Drop into the async queue!
        inject_swarm_chatter(session, role='user', text=user_reply)

        success_dto = ResumeSessionResponseDTO(
            ok=True, message='Swarm chatter injected. Neural pathway active.'
        )
        return Response(
            ResumeSessionResponseSerializer(instance=success_dto).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['get'], url_path='summary_dump')
    def summary_dump(self, request, pk=None):
        """Returns a compact text summary of the session for human review."""
        from django.http import HttpResponse

        session = (
            self.get_queryset()
            .select_related('status', 'identity_disc', 'spike',
                            'spike__spike_train')
            .get(pk=pk)
        )
        turns = (
            session.turns.select_related(
                'status',
                'model_usage_record',
                'model_usage_record__ai_model',
            )
            .prefetch_related('tool_calls__tool')
            .order_by('turn_number')
        )

        lines = []
        lines.append('SESSION SUMMARY DUMP')
        lines.append('=' * 72)
        lines.append(f'Session ID:    {session.id}')
        lines.append(f'Status:        {session.status.name if session.status else "?"}')
        lines.append(f'Identity:      {session.identity_disc.name if session.identity_disc else "Unassigned"}')
        lines.append(f'Created:       {session.created}')
        lines.append(f'Modified:      {session.modified}')
        lines.append(f'Turns:         {turns.count()}')
        if session.spike:
            lines.append(f'Spike:         {session.spike_id}')
            if session.spike.spike_train_id:
                lines.append(f'SpikeTrain:    {session.spike.spike_train_id}')
        lines.append('=' * 72)
        lines.append('')

        for turn in turns:
            lines.append(f'--- TURN {turn.turn_number} [{turn.id}] ---')
            lines.append(f'Status: {turn.status.name if turn.status else "?"}')

            mur = turn.model_usage_record
            if mur:
                model_name = mur.ai_model.name if mur.ai_model else '?'
                lines.append(f'Model:  {model_name}')
                token_line = f'Tokens: in={mur.input_tokens} out={mur.output_tokens}'
                if mur.reasoning_tokens:
                    token_line += f' reasoning={mur.reasoning_tokens}'
                if mur.cache_read_input_tokens:
                    token_line += f' cache_read={mur.cache_read_input_tokens}'
                lines.append(token_line)
                if mur.actual_cost:
                    lines.append(f'Cost:   ${mur.actual_cost}')
                elif mur.estimated_cost:
                    lines.append(f'Est:    ${mur.estimated_cost}')

                # INPUT CONTEXT — what the addons assembled for this turn
                req_payload = mur.request_payload
                if req_payload and isinstance(req_payload, list):
                    lines.append('')
                    lines.append(f'  INPUT CONTEXT ({len(req_payload)} messages):')
                    for idx, msg in enumerate(req_payload):
                        role = msg.get('role', '?')
                        content = msg.get('content', '')
                        tc_list = msg.get('tool_calls', [])
                        tc_id = msg.get('tool_call_id', '')

                        # Role header
                        header = f'  [{idx}] {role.upper()}'
                        if tc_id:
                            name = msg.get('name', '')
                            header += f' (tool_call_id={tc_id}'
                            if name:
                                header += f', name={name}'
                            header += ')'
                        lines.append(header)

                        # Content preview
                        if content and isinstance(content, str):
                            preview = content[:400]
                            if len(content) > 400:
                                preview += f'\n    ... ({len(content)} chars total)'
                            # Indent each line
                            for cl in preview.splitlines():
                                lines.append(f'    {cl}')

                        # Tool calls in the message
                        if tc_list:
                            for tc in tc_list:
                                fn = tc.get('function', {})
                                lines.append(
                                    f'    -> {fn.get("name", "?")}('
                                    f'{fn.get("arguments", "")[:150]})'
                                )

                lines.append('')
                lines.append('  OUTPUT:')

                # Extract assistant message — provider-agnostic
                resp = mur.response_payload or {}
                # Direct format: {role, content, ...}
                if 'role' in resp:
                    msg = resp
                # OpenAI-style: {choices: [{message: {...}}]}
                elif 'choices' in resp:
                    choices = resp.get('choices', [])
                    msg = choices[0].get('message', {}) if choices else {}
                else:
                    msg = {}

                content = msg.get('content', '')
                if content and isinstance(content, str):
                    preview = content[:400]
                    if len(content) > 400:
                        preview += f'... ({len(content)} chars)'
                    lines.append(f'  Content:\n    {preview}')

                # Tool calls from response
                tool_calls_resp = msg.get('tool_calls', [])
                if tool_calls_resp:
                    lines.append(f'  Tool calls ({len(tool_calls_resp)}):')
                    for tc in tool_calls_resp:
                        fn = tc.get('function', {})
                        name = fn.get('name', '?')
                        args_str = fn.get('arguments', '')
                        args_preview = args_str[:200]
                        if len(args_str) > 200:
                            args_preview += '...'
                        lines.append(f'    -> {name}({args_preview})')

            # Tool calls from ORM (tool execution results)
            orm_tool_calls = list(turn.tool_calls.all())
            if orm_tool_calls:
                lines.append(f'  Tool results ({len(orm_tool_calls)}):')
                for tc in orm_tool_calls:
                    tool_name = tc.tool.name if tc.tool else '?'
                    result_preview = ''
                    if tc.result_payload:
                        r = str(tc.result_payload)[:200]
                        if len(str(tc.result_payload)) > 200:
                            r += '...'
                        result_preview = f' => {r}'
                    lines.append(f'    <- {tool_name}{result_preview}')

            lines.append('')

        body = '\n'.join(lines)
        sid = str(session.id)[:8]
        response = HttpResponse(body, content_type='text/plain')
        response['Content-Disposition'] = (
            f'attachment; filename="session_summary_{sid}.log"'
        )
        return response

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Gracefully signals the Frontal Lobe loop to halt at the next turn."""
        session = self.get_object()
        spike = session.spike
        if not spike:
            return Response({'error': 'No associated Spike found.'}, status=400)

        spike.status_id = SpikeStatus.STOPPING
        spike.save(update_fields=['status'])
        return Response(
            {
                'status': 'Halt signal sent. The Cortex will spin down after the current turn.'
            }
        )


class ReasoningTurnViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Deep inspection endpoint for individual cognitive cycles.
    Used by the frontend graph to view the raw Ledger (request/response payloads, tokens, costs).
    """

    queryset = (
        ReasoningTurn.objects.select_related(
            'status',
            'session',
            'model_usage_record',
            'model_usage_record__ai_model',
            'model_usage_record__ai_model_provider',
        )
        .prefetch_related('tool_calls__tool')
        .order_by('-created')
    )

    # Using the serializer you defined earlier!
    serializer_class = serializers.ReasoningTurnSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['session', 'status']
