"""
Central Nervous System (CNS) Tools
===================================

MCP tools for discovering, launching, monitoring, and controlling
Are-Self's neural pathway execution engine.
"""

import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional
from uuid import UUID

from asgiref.sync import sync_to_async

from mcp_server.server import MCPToolRegistry

logger = logging.getLogger(__name__)


def register_cns_tools(registry: MCPToolRegistry) -> None:
    """Register CNS tools on the MCP tool registry."""

    # ----------------------------------------------------------
    # list_neural_pathways
    # ----------------------------------------------------------

    async def list_neural_pathways(
        favorites_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all available neural pathways."""
        from central_nervous_system.models import NeuralPathway

        @sync_to_async
        def _query():
            qs = NeuralPathway.objects.all().order_by('name')
            if favorites_only:
                qs = qs.filter(is_favorite=True)
            return list(
                qs.values('id', 'name', 'description', 'is_favorite')
            )

        rows = await _query()
        return [
            {
                'id': str(r['id']),
                'name': r['name'],
                'description': r['description'],
                'is_favorite': r['is_favorite'],
            }
            for r in rows
        ]

    registry.register(
        name='list_neural_pathways',
        description=(
            'List all available neural pathways that can be '
            'launched as spike trains. Optionally filter to '
            'favorites only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'favorites_only': {
                    'type': 'boolean',
                    'description': 'Only return favorited pathways',
                    'default': False,
                },
            },
        },
        handler=list_neural_pathways,
    )

    # ----------------------------------------------------------
    # get_neural_pathway
    # ----------------------------------------------------------

    async def get_neural_pathway(
        pathway_id: str,
    ) -> Dict[str, Any]:
        """Get pathway details with neurons and axons."""
        from central_nervous_system.models import NeuralPathway

        @sync_to_async
        def _query():
            pathway = NeuralPathway.objects.prefetch_related(
                'neurons__effector', 'axons'
            ).get(id=pathway_id)
            neurons = [
                {
                    'id': str(n.id),
                    'effector_name': (
                        n.effector.name if n.effector else None
                    ),
                    'is_root': n.is_root,
                }
                for n in pathway.neurons.all()
            ]
            axons = [
                {
                    'id': str(a.id),
                    'source_id': str(a.source_id),
                    'target_id': str(a.target_id),
                }
                for a in pathway.axons.all()
            ]
            return {
                'id': str(pathway.id),
                'name': pathway.name,
                'description': pathway.description,
                'neurons': neurons,
                'axons': axons,
            }

        try:
            return await _query()
        except Exception:
            return {'error': 'Pathway %s not found' % pathway_id}

    registry.register(
        name='get_neural_pathway',
        description=(
            'Get detailed information about a neural pathway '
            'including its neurons (nodes) and axons (wires).'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'pathway_id': {
                    'type': 'string',
                    'description': 'UUID of the neural pathway',
                },
            },
            'required': ['pathway_id'],
        },
        handler=get_neural_pathway,
    )

    # ----------------------------------------------------------
    # launch_spike_train
    # ----------------------------------------------------------

    async def launch_spike_train(
        pathway_id: str,
        environment_id: Optional[str] = None,
        cerebrospinal_fluid: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fire a neural pathway — creates and starts a SpikeTrain.

        The optional `cerebrospinal_fluid` dict is merged into every root
        spike of the new train before it fires. Values propagate down-graph
        via the normal provenance copy in _create_spike_from_node, so
        effectors can read them from spike.axoplasm like any other
        context data. This is the MCP equivalent of pre-loading the
        neuron context, but scoped to this single launch.
        """

        seed_csf: Dict[str, Any] = (
            dict(cerebrospinal_fluid) if isinstance(cerebrospinal_fluid, dict) else {}
        )

        @sync_to_async
        def _launch():
            from central_nervous_system.central_nervous_system import CNS

            cns = CNS(
                pathway_id=UUID(pathway_id),
                seed_cerebrospinal_fluid=seed_csf,
            )
            spike_train = cns.spike_train
            pathway_name = (
                spike_train.pathway.name
                if spike_train.pathway
                else 'Unknown'
            )
            cns.start()
            return {
                'spike_train_id': str(spike_train.id),
                'status': 'started',
                'pathway_name': pathway_name,
                'seeded_keys': sorted(seed_csf.keys()),
            }

        try:
            result = await _launch()
            logger.info(
                '[MCP] Launched spike train %s for pathway %s '
                '(seeded keys: %s)',
                result['spike_train_id'][:8],
                pathway_id[:8],
                result['seeded_keys'],
            )
            return result
        except Exception as e:
            logger.error(
                '[MCP] Failed to launch spike train: %s', str(e)
            )
            return {'error': 'Launch failed: %s' % str(e)}

    registry.register(
        name='launch_spike_train',
        description=(
            'Launch a neural pathway execution. Creates a SpikeTrain '
            'and begins firing. Returns the spike_train_id for '
            'monitoring. Pass an optional `cerebrospinal_fluid` dict to '
            'pre-load context data onto every root spike of the new '
            'train — values propagate down-graph like any other '
            'axoplasm state.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'pathway_id': {
                    'type': 'string',
                    'description': 'UUID of the pathway to launch',
                },
                'environment_id': {
                    'type': 'string',
                    'description': (
                        'Optional environment context UUID'
                    ),
                },
                'cerebrospinal_fluid': {
                    'type': 'object',
                    'description': (
                        'Optional flat key/value dict merged into '
                        'the SpikeTrain cerebrospinal_fluid before '
                        'the train fires. Values propagate down-graph '
                        'via provenance. Use this to pre-load prompts, '
                        'targets, or any effector-specific context.'
                    ),
                    'additionalProperties': True,
                },
            },
            'required': ['pathway_id'],
        },
        handler=launch_spike_train,
    )

    # ----------------------------------------------------------
    # get_spike_train_status
    # ----------------------------------------------------------

    async def get_spike_train_status(
        spike_train_id: str,
    ) -> Dict[str, Any]:
        """Check on a running spike train."""
        from central_nervous_system.models import SpikeTrain

        @sync_to_async
        def _query():
            st = SpikeTrain.objects.select_related(
                'status', 'pathway'
            ).prefetch_related(
                'spikes__status', 'spikes__effector'
            ).get(id=spike_train_id)

            spikes = [
                {
                    'id': str(s.id),
                    'effector_name': (
                        s.effector.name if s.effector else None
                    ),
                    'status': (
                        s.status.name if s.status else None
                    ),
                    'created': (
                        s.created.isoformat()
                        if s.created
                        else None
                    ),
                }
                for s in st.spikes.all().order_by('created')
            ]
            return {
                'id': str(st.id),
                'status': st.status.name if st.status else None,
                'pathway_name': (
                    st.pathway.name if st.pathway else None
                ),
                'is_active': st.is_active,
                'created': (
                    st.created.isoformat()
                    if st.created
                    else None
                ),
                'spikes': spikes,
            }

        try:
            return await _query()
        except Exception:
            return {
                'error': 'SpikeTrain %s not found' % spike_train_id,
            }

    registry.register(
        name='get_spike_train_status',
        description=(
            'Get the current status of a spike train execution '
            'including all spikes and their states.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'spike_train_id': {
                    'type': 'string',
                    'description': 'UUID of the spike train',
                },
            },
            'required': ['spike_train_id'],
        },
        handler=get_spike_train_status,
    )

    # ----------------------------------------------------------
    # stop_spike_train
    # ----------------------------------------------------------

    async def stop_spike_train(
        spike_train_id: str,
    ) -> Dict[str, Any]:
        """Gracefully stop a spike train."""

        @sync_to_async
        def _stop():
            from central_nervous_system.central_nervous_system import CNS

            cns = CNS(spike_train_id=UUID(spike_train_id))
            cns.stop_gracefully()
            return {
                'message': 'Stop signal sent.',
                'spike_train_id': spike_train_id,
            }

        try:
            return await _stop()
        except Exception as e:
            logger.error(
                '[MCP] Failed to stop spike train: %s', str(e)
            )
            return {'error': 'Stop failed: %s' % str(e)}

    registry.register(
        name='stop_spike_train',
        description=(
            'Send a graceful stop signal to a running spike train. '
            'In-flight spikes complete before termination.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'spike_train_id': {
                    'type': 'string',
                    'description': 'UUID of the spike train to stop',
                },
            },
            'required': ['spike_train_id'],
        },
        handler=stop_spike_train,
    )

    # ----------------------------------------------------------
    # list_effectors
    # ----------------------------------------------------------

    async def list_effectors() -> List[Dict[str, Any]]:
        """List all available effectors."""
        from central_nervous_system.models import Effector

        @sync_to_async
        def _query():
            return list(
                Effector.objects.all()
                .order_by('name')
                .values('id', 'name', 'description')
            )

        rows = await _query()
        return [
            {
                'id': int(r['id']),
                'name': r['name'],
                'description': r['description'],
            }
            for r in rows
        ]

    registry.register(
        name='list_effectors',
        description=(
            'List all available effectors — the building blocks '
            'that can be wired into neural pathways.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        handler=list_effectors,
    )

    logger.info('[MCP] CNS tools registered (6 tools).')
