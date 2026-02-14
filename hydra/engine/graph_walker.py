import logging

from django.db import transaction

from hydra.models import HydraHead, HydraSpawn, HydraStatusID

logger = logging.getLogger(__name__)


class GraphWalker:
    def __init__(self, spawn_id):
        self.spawn = HydraSpawn.objects.get(id=spawn_id)

    def process_node(self, head: HydraHead):
        """
        Decides how to execute a node based on its definition.
        """
        hydra_node = head.node

        # 0. Check if Node is already finished (e.g. woke up from Delegation)
        # If the head is in a terminal state (SUCCESS/FAILED), we assume it has completed its work
        # and we should proceed to traverse wires. This handles the 'Wake Up' signal.
        if head.status_id in [HydraStatusID.SUCCESS, HydraStatusID.FAILED]:
            logger.info(
                f'[WALKER] Node {head.id} finished ({head.status.name}). Traversing...'
            )
            self._traverse_wires(head)
            return

        # 1. HANDLE SUB-GRAPH (Delegation)
        if hydra_node and hydra_node.invoked_spellbook:
            if head.status_id == HydraStatusID.DELEGATED:
                logger.debug(
                    f'[WALKER] Node {head.id} is already delegated. Skipping.'
                )
                return

            self._spawn_subgraph(head)
            return  # STOP! Do not continue wires. We sleep now.

        # 2. HANDLE STANDARD SPELL
        if head.spell:
            self._execute_spell(head)
            return

        # 3. HANDLE LOGIC/PASSTHROUGH (No Spell, No Subgraph)
        # Just a routing node or empty node
        head.status_id = HydraStatusID.SUCCESS
        head.save(update_fields=['status'])
        self._traverse_wires(head)

    def _spawn_subgraph(self, head: HydraHead):
        """
        Creates the Child Spawn and puts the Parent Node to sleep.
        """
        from hydra.hydra import Hydra

        target_book = head.node.invoked_spellbook

        logger.info(
            f'[WALKER] Node {head.id} spawning subgraph {target_book.name}'
        )

        # A. Create the Child Spawn
        child_spawn = HydraSpawn.objects.create(
            spellbook=target_book,
            parent_head=head,
            context_data=head.spawn.context_data,
            environment=head.spawn.environment,
            status_id=HydraStatusID.CREATED,
        )

        # B. Update Parent Node Status
        head.status_id = HydraStatusID.DELEGATED
        head.save(update_fields=['status'])

        # C. Kickoff the Child
        # We start the Hydra controller for the new spawn
        def start_child():
            Hydra(spawn_id=child_spawn.id).start()

        transaction.on_commit(start_child)
        print(
            f'[WALKER] Node {head.id} delegated execution to Spawn {child_spawn.id}'
        )

    def _execute_spell(self, head: HydraHead):
        """Standard Spell Execution via Celery."""
        from hydra.tasks import cast_hydra_spell

        # Mark as PENDING if not already
        if head.status_id == HydraStatusID.CREATED:
            head.status_id = HydraStatusID.PENDING
            head.save(update_fields=['status'])

        transaction.on_commit(lambda: cast_hydra_spell.delay(head.id))

    def _traverse_wires(self, head: HydraHead):
        """Delegates to Hydra's internal trigger logic."""
        from hydra.hydra import Hydra

        controller = Hydra(spawn_id=self.spawn.id)
        # Using the protected method from Hydra to keep logic centralized
        if hasattr(controller, '_process_graph_triggers'):
            controller._process_graph_triggers(finished_head=head)
        else:
            logger.error('[WALKER] Hydra._process_graph_triggers not found!')
