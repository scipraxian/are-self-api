import logging
import uuid
from typing import Tuple

from asgiref.sync import sync_to_async

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import NeuralPathway, Spike
from central_nervous_system.utils import get_active_environment
from prefrontal_cortex.constants import PFCConstants
from prefrontal_cortex.models import PFCItemStatus, PFCStory, PFCTask

logger = logging.getLogger(__name__)


class PrefrontalCortex:
    """The Compiler: Translates Time into Context and dispatches the execution graph."""

    def __init__(
        self,
        spike_id: uuid.UUID,
        iteration_id: int,
        shift_id: int,
        identity_id: str,
    ):
        self.spike = Spike.objects.get(id=spike_id)
        self.iteration_id = iteration_id
        self.shift_id = shift_id
        self.identity_id = identity_id

    async def compile_and_dispatch(self) -> Tuple[int, str]:
        """Compiles Agile Board context and fires the CNS Non-Blocking drop."""

        # 1. Compile Domain Context
        board_context = await self._query_agile_board()

        # 2. Package the Blackboard
        await self._inject_blackboard(board_context)

        # 3. The Drop (Launch the Frontal Lobe loop)
        return await self._launch_cns_pathway()

    @sync_to_async
    def _query_agile_board(self) -> str:
        """Queries the Agile Board based on the current shift's focus."""
        # Example dynamic compilation based on shift identity
        # In a real implementation, check shift.name (e.g., 'Grooming' vs 'Executing')
        backlog_status = PFCItemStatus.objects.get(id=PFCItemStatus.BACKLOG)
        stories = PFCStory.objects.filter(status=backlog_status)[:5]

        context_lines = ['[AGILE BOARD CONTEXT]']
        for s in stories:
            context_lines.append(f'- Story {s.id}: {s.name}')

        return '\n'.join(context_lines)

    @sync_to_async
    def _inject_blackboard(self, board_context: str) -> None:
        """Injects the compiled routing package into the runtime state."""
        if not isinstance(self.spike.blackboard, dict):
            self.spike.blackboard = {}

        self.spike.blackboard.update(
            {
                'active_iteration_id': self.iteration_id,
                'active_shift_id': self.shift_id,
                'identity_id': self.identity_id,
                'agile_context': board_context,
            }
        )
        self.spike.save(update_fields=['blackboard'])

    @sync_to_async
    def _launch_cns_pathway(self) -> Tuple[int, str]:
        """Finds the Frontal Lobe graph and spins up the asynchronous SpikeTrain."""
        env = get_active_environment(self.spike)

        pathway = NeuralPathway.objects.filter(
            name__icontains=PFCConstants.TARGET_PATHWAY_NAME, environment=env
        ).first()

        if not pathway:
            return 500, PFCConstants.ERR_NO_PATHWAY

        # Initialize the CNS execution
        cns = CNS(pathway_id=pathway.id)

        # VITAL: Link the new SpikeTrain to the current Spike.
        # This acts as the "bridge" carrying the Blackboard context forward.
        cns.spike_train.parent_spike = self.spike
        cns.spike_train.save(update_fields=['parent_spike'])

        cns.start()

        return 200, f'{PFCConstants.MSG_DISPATCHED} {cns.spike_train.id}'
