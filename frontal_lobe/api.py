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
            .select_related(
                'status', 'identity_disc', 'spike', 'spike__spike_train'
            )
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
        lines.append(
            f'Status:        {session.status.name if session.status else "?"}'
        )
        lines.append(
            f'Identity:      {session.identity_disc.name if session.identity_disc else "Unassigned"}'
        )
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
                token_line = (
                    f'Tokens: in={mur.input_tokens} out={mur.output_tokens}'
                )
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
                    lines.append(
                        f'  INPUT CONTEXT ({len(req_payload)} messages):'
                    )
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
                                preview += (
                                    f'\n    ... ({len(content)} chars total)'
                                )
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

    @action(detail=True, methods=['get'], url_path='narrative_dump')
    def narrative_dump(self, request, pk=None):
        """Returns a detailed narrative of session activity with tool
        execution and error summaries."""
        import json

        from django.http import HttpResponse

        session = (
            self.get_queryset()
            .select_related(
                'status',
                'identity_disc',
                'spike',
                'spike__spike_train',
                'conclusion',
            )
            .get(pk=pk)
        )
        turns = (
            session.turns.select_related(
                'status',
                'model_usage_record',
                'model_usage_record__ai_model',
                'model_usage_record__ai_model_provider',
                'model_usage_record__ai_model_provider__provider',
            )
            .prefetch_related('tool_calls__tool')
            .order_by('turn_number')
        )

        id_prefix = str(session.id)[:8]
        identity_name = (
            session.identity_disc.name
            if session.identity_disc
            else 'Unassigned'
        )
        status_name = session.status.name if session.status else '?'
        turn_count = turns.count()
        duration = session.modified - session.created

        lines = []
        lines.append(
            'SESSION NARRATIVE — #%s — %s' % (id_prefix, identity_name)
        )
        lines.append('=' * 88)

        # Status line
        duration_str = '%d:%02d:%02d' % (
            int(duration.total_seconds() // 3600),
            int((duration.total_seconds() % 3600) // 60),
            int(duration.total_seconds() % 60),
        )
        model_name = '?'
        provider_name = '?'
        if turns.exists():
            first_turn = turns.first()
            if first_turn.model_usage_record:
                mur = first_turn.model_usage_record
                if mur.ai_model:
                    model_name = mur.ai_model.name
                if mur.ai_model_provider and mur.ai_model_provider.provider:
                    provider_name = mur.ai_model_provider.provider.key

        lines.append(
            '%s · %d turns · %s' % (status_name, turn_count, duration_str)
        )
        lines.append(
            'Started: %s · Model: %s · %s'
            % (session.created, model_name, provider_name)
        )
        lines.append('')

        # Summary section
        lines.append('SUMMARY')
        if hasattr(session, 'conclusion') and session.conclusion.summary:
            lines.append(session.conclusion.summary)
        else:
            lines.append('Session ended without summary.')
        lines.append('')

        # Parietal Lobe Activity section
        all_tool_calls = []
        for turn in turns:
            for tc in turn.tool_calls.all():
                all_tool_calls.append((turn, tc))

        lines.append('PARIETAL LOBE ACTIVITY (%d calls)' % len(all_tool_calls))
        if all_tool_calls:
            for idx, (turn, tc) in enumerate(all_tool_calls, 1):
                tool_name = tc.tool.name if tc.tool else '?'
                action_name = ''
                field_name = ''

                # Parse arguments JSON to extract mcp_ticket action/field_name
                if tool_name == 'mcp_ticket' and tc.arguments:
                    try:
                        args_dict = json.loads(tc.arguments)
                        action_name = args_dict.get('action', '')
                        field_name = args_dict.get('field_name', '')
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Determine success/failure
                status_indicator = '✓'
                if tc.traceback or (
                    tc.result_payload and isinstance(tc.result_payload, str)
                ):
                    try:
                        result = json.loads(tc.result_payload)
                        if isinstance(result, dict) and not result.get(
                            'ok', True
                        ):
                            status_indicator = '✗'
                    except (json.JSONDecodeError, TypeError):
                        result_lower = tc.result_payload.lower()
                        if 'error' in result_lower or not tc.result_payload:
                            status_indicator = '✗'

                # Format action description
                action_desc = ''
                if action_name and field_name:
                    action_desc = '%s %s' % (action_name, field_name)
                elif action_name:
                    action_desc = action_name
                elif field_name:
                    action_desc = 'set %s' % field_name

                line = '  T%d   %s' % (idx, tool_name)
                if action_desc:
                    line += '  %s' % action_desc
                line += '        %s' % status_indicator
                lines.append(line)
        lines.append('')

        # Engrams section
        engrams = session.engrams.all()
        engram_names = ', '.join([e.name for e in engrams])
        if not engram_names:
            engram_names = 'none formed'
        lines.append('ENGRAMS: %s' % engram_names)
        lines.append('')

        # Errors section
        errors = []
        for turn in turns:
            for tc in turn.tool_calls.all():
                if tc.traceback:
                    error_text = tc.traceback.split('\n')[0][:60]
                    if len(tc.traceback) > 60:
                        error_text += '...'
                    tool_name = tc.tool.name if tc.tool else '?'
                    errors.append(
                        'T%d: %s — %s'
                        % (
                            turn.turn_number,
                            tool_name,
                            error_text,
                        )
                    )
                elif tc.result_payload and isinstance(tc.result_payload, str):
                    try:
                        result = json.loads(tc.result_payload)
                        if isinstance(result, dict) and not result.get(
                            'ok', True
                        ):
                            error_msg = result.get('error', 'Unknown error')[
                                :60
                            ]
                            if len(str(error_msg)) > 60:
                                error_msg += '...'
                            tool_name = tc.tool.name if tc.tool else '?'
                            errors.append(
                                'T%d: %s — %s'
                                % (turn.turn_number, tool_name, error_msg)
                            )
                    except (json.JSONDecodeError, TypeError):
                        pass

        lines.append('ERRORS (%d):' % len(errors))
        if errors:
            for error in errors:
                lines.append('  %s' % error)
        lines.append('')

        # Token summary section
        if turns.exists():
            total_in = 0
            total_out = 0
            for turn in turns:
                if turn.model_usage_record:
                    mur = turn.model_usage_record
                    total_in += mur.input_tokens or 0
                    total_out += mur.output_tokens or 0

            avg_in = int(total_in / turn_count) if turn_count > 0 else 0
            avg_out = int(total_out / turn_count) if turn_count > 0 else 0

            lines.append('TOKEN SUMMARY:')
            lines.append(
                '  Total: %d in · %d out · Avg/turn: %d in · %d out'
                % (total_in, total_out, avg_in, avg_out)
            )

        body = '\n'.join(lines)
        response = HttpResponse(body, content_type='text/plain')
        response['Content-Disposition'] = (
            'attachment; filename="session_narrative_%s.log"' % id_prefix
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
