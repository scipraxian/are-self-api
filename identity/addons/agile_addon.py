from django.db.models import Q

from frontal_lobe.models import ReasoningTurn
from identity.addons.addon_package import AddonPackage
from identity.models import IdentityDisc, IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory
from temporal_lobe.models import Shift


def sifting_pm(identity_disc, environment_id) -> str:
    """The Sifting PM reviews work and moves it to the backlog."""
    success = False
    statements = []
    statements.append(
        f'ROLE: Sifting PM - Refine and/or Create Epics and Stories.'
    )
    statements.append('PM == NO CODE == Planning and Oversight')
    statements.append(f'ENVIRONMENT: {environment_id}')
    epics = PFCEpic.objects.filter(
        (
            Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
            | Q(status_id=PFCItemStatus.BACKLOG)
        )
        & Q(environment=environment_id)
    )
    if epics.count():
        success = True
        statements.append('Epics in need of refinement:')
        for epic in epics:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{epic.id}'}}) | {epic.name}"
            )

    stories = PFCStory.objects.filter(
        (
            Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
            | Q(status_id=PFCItemStatus.BACKLOG)
        )
        & Q(epic__environment_id=environment_id)
    )
    if stories.count():
        success = True
        statements.append('Stories in need of refinement:')
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )

    if not success:
        statements.append('No stories or epics in need of refinement.')
        statements.append('Review everything and make more where necessary.')

    return '\n'.join(statements)


def pre_planning_pm(identity_disc, environment_id) -> str:
    """The Pre-Planning PM queries the entire board and chooses what is selected
    for development."""
    success = False
    statements = []
    statements.append(
        f'ROLE: Pre-Planning PM - Choose epics and stories and set them to selected for development.'
    )
    statements.append('PM == NO CODE == Planning and Oversight')
    statements.append(f'ENVIRONMENT: {environment_id}')
    epics = PFCEpic.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG) & Q(environment=environment_id)
    )
    if epics.count():
        success = True
        statements.append('Epics to consider for development:')
        for epic in epics:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{epic.id}'}}) | {epic.name}"
            )

    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG)
        & Q(epic__environment_id=environment_id)
    )
    if stories.count():
        success = True
        statements.append('Stories to consider for development:')
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )

    selected_and_in_progress_stories = PFCStory.objects.filter(
        (
            Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
            | Q(status_id=PFCItemStatus.IN_PROGRESS)
        )
        & Q(epic__environment_id=environment_id)
    )

    if selected_and_in_progress_stories.count():
        success = True
        statements.append('Stories already selected:')
        for story in selected_and_in_progress_stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name} | {story.status.name}"
            )

    if not success:
        return sifting_pm(identity_disc, environment_id)

    return '\n'.join(statements)


def planning_pm(identity_disc, environment_id) -> str:
    """The Planning PM has no role."""
    return sifting_pm(identity_disc, environment_id)


def executing_pm(identity_disc, environment_id) -> str:
    """The Executing PM has no role."""
    return sifting_pm(identity_disc, environment_id)


def post_execution_pm(identity_disc, environment_id) -> str:
    """Are there items for review?"""

    success = False
    statements = []
    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.IN_REVIEW)
        & Q(epic__environment_id=environment_id)
    )
    if stories.count():
        success = True

        statements.append(
            f'ROLE: Post Execution PM - Review stories and epics, upgrade to BLOCKED_BY_USER if they pass the DoD (Definition of Done).'
        )
        statements.append('PM == NO CODE == Planning and Oversight')
        statements.append(f'ENVIRONMENT: {environment_id}')
        statements.append('Review as many stories as you have turns to do so.')
        statements.append(
            "If a story or epic does not meet the DoD, use mcp_ticket with action='comment', and then set it back to SELECTED_FOR_DEVELOPMENT."
        )
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )

    if success:
        return '\n'.join(statements)
    else:
        return sifting_pm(identity_disc, environment_id)


def sleeping_pm(identity_disc, environment_id) -> str:
    """The Sleeping PM has no tickets."""
    return (
        'You may now sleep, these turns are yours to learn and grow. '
        'Improve your memories, and learn from your previous work.'
    )


def bidding_worker(identity_disc, environment_id) -> str:
    """The Worker BIDs on the backlog."""
    statements = []
    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG)
        & Q(owning_disc__isnull=True)
        & Q(epic__environment_id=environment_id)
        & Q(complexity=0)
    )
    if stories.count():
        statements.append(
            'A BID is how many turns you think it will take to complete a story. These stories are in need of a BID:'
        )
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )
        return '\n'.join(statements)
    else:
        return sifting_worker(identity_disc, environment_id)


def sifting_worker(identity_disc, environment_id) -> str:
    """The Sifting Worker cleans items in the backlog and/or
    Tasks to complete existing Stories. Only deal with unassigned stories."""
    success = False
    statements = []
    statements.append(f'ENVIRONMENT: {environment_id}')
    statements.append(
        'ROLE: Sifting Worker - Create and Improve Stories and Tasks so they meet Definition of Ready (DoR) so a PM may move it to the BACKLOG.'
    )
    statements.append('This is a non-execution Shift. NO CODE')
    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
        & (Q(owning_disc__isnull=True) | Q(owning_disc=identity_disc))
        & Q(epic__environment_id=environment_id)
    )
    if stories.count():
        success = True
        statements.append('Stories in need of refinement:')
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )

    if not success:
        statements.append('No stories need of refinement.')
        statements.append('Review everything and make more where necessary.')

    return '\n'.join(statements)


def executing_worker(identity_disc, environment_id) -> str:
    """The Executing Worker is assigned or continues work on assigned tickets."""
    success = False
    statements = []
    statements.append(f'ENVIRONMENT: {environment_id}')
    statements.append('ROLE: Executing Worker - Execute stories and tasks.')
    statements.append(
        'This is an EXECUTION Shift. Fulfill Assertions to the best of your ability.'
    )
    my_stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
        & Q(owning_disc=identity_disc)
        & Q(epic__environment_id=environment_id)
    )
    if my_stories.count():
        success = True
        statements.append('You own the following stories:')
        for story in my_stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )
    available_stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
        & Q(owning_disc__isnull=True)
        & Q(epic__environment_id=environment_id)
    )
    if available_stories.count():
        success = True
        statements.append('You may work on the following stories:')
        for story in available_stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name}"
            )
    if not success:
        statements.append('No stories to work on.')
        statements.append('Review everything and make more where necessary.')
    return '\n'.join(statements)


def sleeping_worker(identity_disc, environment_id) -> str:
    """The Sleeping Worker has no tickets."""
    return (
        'You may now sleep, these turns are yours to learn and grow. '
        'Improve your memories, and learn from your previous work.'
    )


class AgilePromptBuilder:
    def __init__(self, package: AddonPackage):
        self.package = package
        self.iteration_id = self.package.iteration
        self.iteration_shift = None
        self.iteration = None
        self.environment_id = None
        self.identity_disc = None
        self.turn_number = None
        self.reasoning_turn = None
        self.context_lines = []

    def _extract_package(self):
        if not self.iteration_id or self.package.reasoning_turn_id is None:
            return  # Skip all DB queries, we are in preview mode!

        if self.package.identity_disc:
            self.identity_disc = IdentityDisc.objects.select_related(
                'identity'
            ).get(id=self.package.identity_disc)
        self.turn_number = self.package.turn_number
        self.reasoning_turn = ReasoningTurn.objects.select_related(
            'session__participant__iteration_shift__shift_iteration',
            'session__participant__iteration_shift__shift',
        ).get(id=self.package.reasoning_turn_id)

        self.iteration_shift = (
            self.reasoning_turn.session.participant.iteration_shift
        )
        self.iteration = self.iteration_shift.shift_iteration
        self.environment_id = self.iteration.environment_id
        self.shift = self.iteration_shift.shift

    def build_prompt(self) -> str:
        self._extract_package()

        if not self.identity_disc:
            return '[AGILE BOARD CONTEXT: UI Preview Mode - No Active Disc Assigned]'
        if not getattr(self, 'shift', None) or not self.identity_disc:
            return '[AGILE BOARD CONTEXT: UI Preview Mode - No Active Shift or Disc Assigned]'
        self.context_lines = [
            '=========================================',
            f' AGILE BOARD CONTEXT | SHIFT: {self.shift.name}',
            '=========================================',
        ]
        self.context_lines.append(
            "Use mcp_ticket with action='create', 'read', 'update', 'search', or 'comment' to manage tickets. Prefer 'read' and 'update' with only an item_id and payload; the system will infer EPIC/STORY/TASK from the UUID."
        )
        self.context_lines.append(
            'Ticket status values in order by ("id", "name") are: [(1, "Backlog"), (2, "Selected for Development"), (3, "In Progress"), (4, "Blocked by User"), (5, "Done"), (6, "Needs Refinement"), (7, "Will not do.")]'
        )
        identity_type_id = self.identity_disc.identity.identity_type_id
        shift_id = self.shift.id

        match shift_id:
            case Shift.SIFTING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            sifting_pm(self.identity_disc, self.environment_id)
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            bidding_worker(
                                self.identity_disc, self.environment_id
                            )
                        )
            case Shift.PRE_PLANNING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            pre_planning_pm(
                                self.identity_disc, self.environment_id
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            sifting_worker(
                                self.identity_disc, self.environment_id
                            )
                        )
            case Shift.PLANNING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            planning_pm(self.identity_disc, self.environment_id)
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            sifting_worker(
                                self.identity_disc, self.environment_id
                            )
                        )
            case Shift.EXECUTING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            executing_pm(
                                self.identity_disc, self.environment_id
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            executing_worker(
                                self.identity_disc, self.environment_id
                            )
                        )
            case Shift.POST_EXECUTION:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            post_execution_pm(
                                self.identity_disc, self.environment_id
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            bidding_worker(
                                self.identity_disc, self.environment_id
                            )
                        )
            case Shift.SLEEPING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            sleeping_pm(self.identity_disc, self.environment_id)
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            sleeping_worker(
                                self.identity_disc, self.environment_id
                            )
                        )
        return '\n'.join(self.context_lines)


def agile_addon(package: AddonPackage) -> str:
    """
    Identity Addon: Dynamically injects the active Agile Board context into the system prompt.
    Adapts the ticket payload based on the current Temporal Shift (Grooming, Planning, Executing).
    """
    builder = AgilePromptBuilder(package)
    return builder.build_prompt()
