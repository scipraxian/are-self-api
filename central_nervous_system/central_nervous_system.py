import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone

from config.celery import app as celery_app
from environments.models import ProjectEnvironment
from peripheral_nervous_system.models import NerveTerminalRegistry, NerveTerminalStatus

from .models import (
    Axon,
    AxonType,
    CNSDistributionModeID,
    CNSStatusID,
    NeuralPathway,
    Neuron,
    NeuronContext,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from .tasks import fire_spike

logger = logging.getLogger(__name__)


class CNS:
    """
    The High-Level Job Manager (Graph Edition).

    Architecture:
    -------------
    Acts as the Synchronous Orchestrator using 'Database Locking'.

    Graph Logic:
    1. Roots: Effectors with no incoming axons start first.
    2. Triggers: When a Spike finishes, we check 'Axon'.
    3. Provenance: We track the execution history to prevent infinite loops (mostly).
    """

    STALE_PENDING_TIMEOUT = timedelta(minutes=5)

    def __init__(
        self,
        pathway_id: Optional[uuid.UUID] = None,
        spike_train_id: Optional[uuid.UUID] = None,
    ):
        if spike_train_id:
            self.spike_train = SpikeTrain.objects.get(id=spike_train_id)
        elif pathway_id:
            self.spike_train = self._create_spawn(pathway_id)
        else:
            raise ValueError('Must provide either spike_train_id or pathway_id')

    def start(self) -> None:
        """Ignites the spike_train idempotently."""
        with transaction.atomic():
            spike_train = SpikeTrain.objects.select_for_update().get(
                id=self.spike_train.id
            )

            if spike_train.status_id != SpikeTrainStatus.CREATED:
                logger.warning(
                    f'[CNS] SpikeTrain {spike_train.id} already started.'
                )
                return

            spike_train.status_id = SpikeTrainStatus.RUNNING
            spike_train.save(update_fields=['status'])

        self.dispatch_next_wave()

    def terminate(self) -> None:
        """Aborts the spike_train immediately (Hard Kill)."""
        task_ids_to_revoke = []

        with transaction.atomic():
            spike_train = SpikeTrain.objects.select_for_update().get(
                id=self.spike_train.id
            )

            if spike_train.status_id in [
                SpikeTrainStatus.SUCCESS,
                SpikeTrainStatus.FAILED,
            ]:
                return

            running_heads = list(
                spike_train.spikes.select_for_update().filter(
                    status_id__in=[
                        SpikeStatus.RUNNING,
                        SpikeStatus.PENDING,
                    ]
                )
            )

            for spike in running_heads:
                if spike.celery_task_id:
                    task_ids_to_revoke.append(str(spike.celery_task_id))

                spike.status_id = SpikeStatus.ABORTED
                spike.execution_log += (
                    '\n[CNS] Terminated by User (Signal Sent).\n'
                )
                spike.save(update_fields=['status', 'execution_log'])

            spike_train.status_id = SpikeTrainStatus.FAILED
            spike_train.save(update_fields=['status'])

        for task_id in task_ids_to_revoke:
            try:
                celery_app.control.revoke(task_id, terminate=False)
            except Exception as e:
                logger.warning(f'Failed to revoke task {task_id}: {e}')

        logger.info(f'[CNS] SpikeTrain {self.spike_train.id} Terminated.')

    def stop_gracefully(self) -> None:
        """
        Signals active spikes to stop gracefully.
        Sets status to STOPPING.
        """

        with transaction.atomic():
            spike_train = SpikeTrain.objects.select_for_update().get(
                id=self.spike_train.id
            )

            active_heads = spike_train.spikes.select_for_update().filter(
                status_id__in=[
                    SpikeStatus.RUNNING,
                    SpikeStatus.PENDING,
                ]
            )

            count = active_heads.update(
                status_id=SpikeStatus.STOPPING, modified=timezone.now()
            )

            if count > 0:
                spike_train.status_id = SpikeTrainStatus.STOPPING
                spike_train.save(update_fields=['status'])

            logger.info(
                f'[CNS] SpikeTrain {self.spike_train.id}: '
                f'stop_gracefully signaled {count} spikes.'
            )

    def poll(self) -> None:
        """Maintenance Pulse."""
        with transaction.atomic():
            # 1. Ghost Detection
            active_heads = self.spike_train.spikes.select_for_update().filter(
                status_id=SpikeStatus.RUNNING
            )
            for spike in active_heads:
                if not spike.celery_task_id:
                    continue
                res = AsyncResult(str(spike.celery_task_id))
                if res.ready() and res.state in ['FAILURE', 'REVOKED']:
                    logger.warning(f'[CNS] Ghost Task {spike.id}')
                    spike.status_id = SpikeStatus.FAILED
                    spike.execution_log += (
                        f'\n[CNS POLL] Task Crash: {res.info}\n'
                    )
                    spike.save(update_fields=['status', 'execution_log'])

            # 2. Stale Pending Detection
            stale_threshold = timezone.now() - self.STALE_PENDING_TIMEOUT
            stale_heads = self.spike_train.spikes.select_for_update().filter(
                status_id=SpikeStatus.PENDING,
                modified__lt=stale_threshold,
            )
            for spike in stale_heads:
                spike.status_id = SpikeStatus.FAILED
                spike.execution_log += '\n[CNS POLL] Timeout.\n'
                spike.save(update_fields=['status', 'execution_log'])

        # 3. Trigger Graph Logic
        self.dispatch_next_wave()

    def view(self) -> Dict[str, Any]:
        """Serializer for UI."""
        return {
            'id': str(self.spike_train.id),
            'status': self.spike_train.status.name,
            'progress': 0.0,
            'current_wave': 0,
            'spikes': [
                {
                    'id': str(h.id),
                    'name': h.effector.talos_executable.name,
                    'node_id': h.neuron_id if h.neuron else None,
                    'status_id': h.status.id,
                    'status_name': h.status.name,
                    'log_preview': (h.application_log or '')[:150],
                }
                for h in self.spike_train.spikes.all()
                .select_related('effector', 'status', 'neuron')
                .order_by('created')
            ],
        }

    # =========================================================================
    # Internal Logic
    # =========================================================================

    def _create_spawn(self, pathway_id: uuid.UUID) -> SpikeTrain:
        book = NeuralPathway.objects.get(id=pathway_id)
        active_env = ProjectEnvironment.objects.filter(selected=True).first()
        spike_train = SpikeTrain.objects.create(
            pathway=book,
            status_id=SpikeTrainStatus.CREATED,
            environment=active_env,
        )
        self.spike_train = spike_train
        return spike_train

    def dispatch_next_wave(self) -> None:
        """
        Graph Dispatcher:
        1. If no spikes exist, launch Roots.
        2. If spikes finished, follow Wires.
        """
        with transaction.atomic():
            # Refresh to ensure we catch STOPPING state updates
            self.spike_train.refresh_from_db()

            if self.spike_train.status_id == SpikeTrainStatus.STOPPING:
                logger.info(
                    f'[CNS] SpikeTrain {self.spike_train.id} is STOPPING. Halting graph traversal.'
                )
                self._finalize_spawn_unsafe()
                return

            spikes = self.spike_train.spikes.select_for_update().all()

            if not spikes.exists():
                self._dispatch_graph_roots()
                return

            # Trigger Check: Include STOPPED as a terminal state that might allow flow (e.g. Failure paths)
            # Depending on desired logic, STOPPED might trigger 'Failure' axons or just end the graph.
            # For now, we treat STOPPED as a terminal state that halts flow.
            finished_spikes = spikes.filter(
                status_id__in=[SpikeStatus.SUCCESS, SpikeStatus.FAILED]
            )

            parents_with_children = Spike.objects.filter(
                spike_train=self.spike_train, provenance__isnull=False
            ).values_list('provenance_id', flat=True)

            for spike in finished_spikes:
                if spike.id in parents_with_children:
                    continue

                self._process_graph_triggers(spike)

            self._finalize_spawn_unsafe()

    def _dispatch_graph_roots(self) -> None:
        """Execute all Begin Play neurons."""
        all_nodes = self.spike_train.pathway.neurons.all()
        root_nodes = all_nodes.filter(is_root=True)

        if not root_nodes.exists() and all_nodes.exists():
            logger.error(
                f'[CNS] No Begin Play node found '
                f'for {self.spike_train.pathway.name}!'
            )
            return

        for node in root_nodes:
            self._create_spike_from_node(node, provenance=None)

    def _process_graph_triggers(self, finished_spike: Spike) -> None:
        """Follows the axons from a finished spike based on Status Logic."""
        if not finished_spike.neuron:
            return

        valid_wire_types = []
        valid_wire_types.append(AxonType.TYPE_FLOW)

        if finished_spike.status_id == SpikeStatus.SUCCESS:
            valid_wire_types.append(AxonType.TYPE_SUCCESS)
        elif finished_spike.status_id == SpikeStatus.FAILED:
            valid_wire_types.append(AxonType.TYPE_FAILURE)

        axons = Axon.objects.filter(
            pathway=self.spike_train.pathway,
            source=finished_spike.neuron,
            type_id__in=valid_wire_types,
        )

        if not axons.exists():
            return

        logger.info(
            f'[CNS] Triggering {axons.count()} '
            f'axons from Spike {finished_spike.id}'
        )

        for wire in axons:
            self._create_spike_from_node(
                neuron=wire.target, provenance=finished_spike
            )

    def _create_spike_from_node(
        self, neuron: Neuron, provenance: Optional[Spike]
    ):
        starting_blackboard = {}

        if provenance:
            starting_blackboard = provenance.blackboard.copy()
        elif self.spike_train.parent_spike:
            starting_blackboard = (
                self.spike_train.parent_spike.blackboard.copy()
            )
            node_args = NeuronContext.objects.filter(
                neuron=self.spike_train.parent_spike.neuron
            )
            for arg in node_args:
                if arg.key:
                    starting_blackboard[arg.key] = arg.value

        seed_spike = Spike.objects.create(
            spike_train=self.spike_train,
            neuron=neuron,
            effector=neuron.effector,
            provenance=provenance,
            target=None,
            status_id=SpikeStatus.CREATED,
            blackboard=starting_blackboard,
        )

        if getattr(neuron, 'invoked_pathway', None):
            self._spawn_subgraph(seed_spike)
            return

        if getattr(neuron, 'distribution_mode', None):
            mode = neuron.distribution_mode_id
        else:
            mode = neuron.effector.distribution_mode_id

        if mode == CNSDistributionModeID.ALL_ONLINE_AGENTS:
            self._dispatch_fleet_wave(seed_spike)
        elif mode == CNSDistributionModeID.SPECIFIC_TARGETS:
            self._dispatch_pinned_wave(seed_spike)
        elif mode == CNSDistributionModeID.ONE_AVAILABLE_AGENT:
            self._dispatch_first_responder(seed_spike)
        else:
            self._prepare_and_dispatch(seed_spike)

    def _dispatch_fleet_wave(self, seed_spike: Spike) -> None:
        agents = NerveTerminalRegistry.objects.filter(
            status_id=NerveTerminalStatus.ONLINE
        )

        if not agents.exists():
            seed_spike.status_id = CNSStatusID.FAILED
            seed_spike.execution_log = (
                '[CNS] No agents online for fleet broadcast.'
            )
            seed_spike.save()
            return

        for agent in agents:
            self._clone_and_dispatch_spike(seed_spike, agent)

        seed_spike.delete()

    def _dispatch_pinned_wave(self, seed_spike: Spike) -> None:
        targets = seed_spike.effector.specific_targets.all()
        for t in targets:
            self._clone_and_dispatch_spike(seed_spike, t.target)
        seed_spike.delete()

    def _dispatch_first_responder(self, seed_spike: Spike) -> None:
        agent = (
            NerveTerminalRegistry.objects.filter(status_id=NerveTerminalStatus.ONLINE)
            .order_by('last_seen')
            .first()
        )

        if not agent:
            seed_spike.status_id = CNSStatusID.FAILED
            seed_spike.execution_log = '[CNS] No agents available.'
            seed_spike.save()
            return

        self._clone_and_dispatch_spike(seed_spike, agent)
        seed_spike.delete()

    def _clone_and_dispatch_spike(self, seed: Spike, agent: NerveTerminalRegistry):
        new_spike = Spike.objects.create(
            spike_train=seed.spike_train,
            neuron=seed.neuron,
            effector=seed.effector,
            provenance=seed.provenance,
            target=agent,
            status_id=SpikeStatus.PENDING,
            blackboard=seed.blackboard.copy(),
        )
        transaction.on_commit(lambda: fire_spike.delay(new_spike.id))

    def _prepare_and_dispatch(self, spike: Spike) -> None:
        spike.status_id = SpikeStatus.PENDING
        spike.save()
        transaction.on_commit(lambda: fire_spike.delay(spike.id))

    def _finalize_spawn_unsafe(self) -> None:
        """Determines final status."""
        active = self.spike_train.spikes.filter(
            status_id__in=[
                SpikeStatus.CREATED,
                SpikeStatus.PENDING,
                SpikeStatus.RUNNING,
                SpikeStatus.DELEGATED,
                SpikeStatus.STOPPING,
            ]
        )
        if active.exists():
            return

        if self.spike_train.status_id == SpikeTrainStatus.STOPPING:
            new_status = SpikeTrainStatus.STOPPED
        else:
            new_status = SpikeTrainStatus.SUCCESS

        if self.spike_train.status_id != new_status:
            self.spike_train.status_id = new_status
            self.spike_train.save(update_fields=['status'])
            transaction.on_commit(
                lambda: self._trigger_completion_signals(new_status)
            )

    def _trigger_completion_signals(self, status_id: int) -> None:
        from .signals import spawn_failed, spawn_success

        sender = self.spike_train.__class__
        if status_id == SpikeTrainStatus.FAILED:
            spawn_failed.send(sender=sender, spike_train=self.spike_train)
        elif status_id == SpikeTrainStatus.SUCCESS:
            spawn_success.send(sender=sender, spike_train=self.spike_train)

    def _calculate_progress(self) -> float:
        return 0.0

    def _spawn_subgraph(self, spike: Spike) -> None:
        """
        Creates the Child SpikeTrain and puts the Parent Spike to sleep (DELEGATED).
        """
        target_pathway = spike.neuron.invoked_pathway
        logger.info(
            f'[CNS] Spike {spike.id} spawning subgraph {target_pathway.name}'
        )

        # A. Create the Child SpikeTrain
        child_train = SpikeTrain.objects.create(
            pathway=target_pathway,
            parent_spike=spike,
            environment=self.spike_train.environment,
            status_id=SpikeTrainStatus.CREATED,
        )

        # B. Update Parent Spike Status
        spike.status_id = SpikeStatus.DELEGATED
        spike.save(update_fields=['status'])

        # C. Kickoff the Child directly
        def start_child():
            CNS(spike_train_id=child_train.id).start()

        transaction.on_commit(start_child)
        logger.info(
            f'[CNS] Spike {spike.id} delegated execution to SpikeTrain {child_train.id}'
        )
