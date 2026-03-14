from django.db.models import Q

from frontal_lobe.models import ReasoningTurn
from identity.addons.addon_package import AddonPackage
from identity.models import IdentityDisc, IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory
from temporal_lobe.models import Shift


def sifting_pm(identity_disc, environment_id, turn_number) -> str:
    """The Sifting PM reviews work and moves it to the backlog."""
    success = False
    statements = []
    if turn_number % 3 == 1:
        statements.append(
            'DoR: Definition of Ready (DoR) is a set of criteria that must be met for a ticket to be considered ready for development. It ensures that the ticket is well-defined, has clear acceptance criteria, and is free from major issues that would impede development progress.'
            'SHIFT: SIFTING ROLE: PM GOAL: Refine NEEDS_REFINEMENT tickets to meet DoR.'
            'RULES: Use mcp_ticket to populate at least the following fields:'
        )
        statements.append('perspective: The "why" and "who".')
        statements.append('assertions: Bulleted, testable completion steps.')
        statements.append('outside: What NOT to do.')
        statements.append('dod_exceptions: Deviations from standard Done.')
        statements.append('dependencies: Other tickets this one depends on.')
        statements.append('demo_specifics: How and to whom success is proven.')
        statements.append(
            'If you dont know enough to fill in the above, ask questions in the comments and block for human.'
        )
        statements.append('PM == NO CODE == Planning and Oversight')
        statements.append(f'ENVIRONMENT: {environment_id}')
        epics = PFCEpic.objects.filter(
            Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
            & Q(environment=environment_id)
        )
        if epics.count():
            success = True
            statements.append(
                'Epics in this environment which need of refinement:'
            )
            for epic in epics:
                statements.append(
                    f"mcp_ticket(action='read', item_id='{epic.id}') | {epic.name}"
                )

        stories = PFCStory.objects.filter(
            Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
            & Q(epic__environment_id=environment_id)
        )
        if stories.count():
            success = True
            statements.append(
                'Stories in this environment in need of refinement:'
            )
            for story in stories:
                statements.append(
                    f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
                )

        if not success:
            statements.append('No stories or epics in need of refinement.')
            statements.append(
                'Review everything and make more where necessary.'
            )

    return '\n'.join(statements)


def pre_planning_pm(identity_disc, environment_id, turn_number) -> str:
    """The Pre-Planning PM queries the entire board and chooses what is selected
    for development."""
    success = False
    statements = []
    statements.append(
        f'ROLE: Pre-Planning PM - Choose BACKLOG epics and stories and set them to selected for development.'
    )
    statements.append('PM == NO CODE == Planning and Oversight')
    statements.append(f'ENVIRONMENT: {environment_id}')
    epics = PFCEpic.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG) & Q(environment=environment_id)
    )
    if epics.exists():
        success = True
        statements.append('Epics to consider for development:')
        for epic in epics:
            statements.append(
                f"mcp_ticket(action='read', item_id='{epic.id}') | {epic.name}"
            )

    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG)
        & Q(epic__environment_id=environment_id)
    )
    if stories.exists():
        success = True
        statements.append('Stories to consider for development:')
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
            )

    selected_and_in_progress_stories = PFCStory.objects.filter(
        (
            Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
            | Q(status_id=PFCItemStatus.IN_PROGRESS)
        )
        & Q(epic__environment_id=environment_id)
    )

    if selected_and_in_progress_stories.exists():
        success = True
        statements.append('Stories already selected:')
        for story in selected_and_in_progress_stories:
            statements.append(
                f"mcp_ticket(action='read', params={{'item_id': '{story.id}'}}) | {story.name} | {story.status.name}"
            )

    if not success:
        return sifting_pm(identity_disc, environment_id, turn_number)

    return '\n'.join(statements)


def planning_pm(identity_disc, environment_id, turn_number) -> str:
    """The Planning PM has no role."""
    return sifting_pm(identity_disc, environment_id, turn_number)


def executing_pm(identity_disc, environment_id, turn_number) -> str:
    """The Executing PM has no role."""
    return sifting_pm(identity_disc, environment_id, turn_number)


def post_execution_pm(identity_disc, environment_id, turn_number) -> str:
    """Are there items for review?"""

    success = False
    statements = []
    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.IN_REVIEW)
        & Q(epic__environment_id=environment_id)
    )
    if stories.exists():
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
                f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
            )

    if success:
        return '\n'.join(statements)
    else:
        return sifting_pm(identity_disc, environment_id, turn_number)


def sleeping_pm(identity_disc, environment_id, turn_number) -> str:
    """The Sleeping PM has no tickets."""
    return (
        'You may now sleep, these turns are yours to learn and grow. '
        'Improve your memories, and learn from your previous work.'
    )


def bidding_worker(identity_disc, environment_id, turn_number) -> str:
    """The Worker BIDs on the backlog."""
    statements = []
    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG)
        & Q(owning_disc__isnull=True)
        & Q(epic__environment_id=environment_id)
        & Q(complexity=0)
    )
    if stories.exists():
        statements.append(
            'A BID is how many turns you think it will take to complete a story. These stories are in need of a BID:'
        )
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
            )
        return '\n'.join(statements)
    else:
        return sifting_worker(identity_disc, environment_id, turn_number)


def sifting_worker(identity_disc, environment_id, turn_number) -> str:
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
    if stories.exists():
        success = True
        statements.append('Stories in need of refinement:')
        for story in stories:
            statements.append(
                f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
            )

    if not success:
        statements.append('No stories need of refinement.')
        statements.append('Review everything and make more where necessary.')

    return '\n'.join(statements)


def executing_worker(identity_disc, environment_id, turn_number) -> str:
    """The Executing Worker is assigned or continues work on assigned tickets."""
    success = False
    statements = []
    statements.append(f'ENVIRONMENT: {environment_id}')
    statements.append('ROLE: Executing Worker - Execute stories and tasks.')
    statements.append(
        'This is an EXECUTION Shift. Fulfill Assertions to the best of your ability.'
    )
    if turn_number % 3 == 1:
        my_stories = PFCStory.objects.filter(
            Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
            & Q(owning_disc=identity_disc)
            & Q(epic__environment_id=environment_id)
        )
        if my_stories.exists():
            success = True
            statements.append('You own the following stories:')
            for story in my_stories:
                statements.append(
                    f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
                )
        available_stories = PFCStory.objects.filter(
            Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
            & Q(owning_disc__isnull=True)
            & Q(epic__environment_id=environment_id)
        )
        if available_stories.exists():
            success = True
            statements.append('You may work on the following stories:')
            for story in available_stories:
                statements.append(
                    f"mcp_ticket(action='read', item_id='{story.id}') | {story.name}"
                )
        if not success:
            statements.append('No stories to work on.')
            statements.append(
                'Review everything and make more where necessary.'
            )
    return '\n'.join(statements)


def sleeping_worker(identity_disc, environment_id, turn_number) -> str:
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
        self.shift_id = None

    def _extract_package(self):
        if not self.iteration_id or self.package.reasoning_turn_id is None:
            return  # Skip all DB queries, we are in preview mode!

        if self.package.identity_disc:
            self.identity_disc = IdentityDisc.objects.select_related(
                'identity_type'
            ).get(id=self.package.identity_disc)
        self.turn_number = self.package.turn_number

        self.environment_id = getattr(self.package, 'environment_id', None)
        self.shift_id = getattr(self.package, 'shift_id', None)

    def build_prompt(self) -> str:
        self._extract_package()

        if not self.identity_disc:
            return '[AGILE BOARD CONTEXT: UI Preview Mode - No Active Disc Assigned]'
        if not getattr(self, 'shift', None) or not self.identity_disc:
            return '[AGILE BOARD CONTEXT: UI Preview Mode - No Active Shift or Disc Assigned]'
        if self.turn_number % 3 == 1:
            self.context_lines = [
                '=========================================',
                f' AGILE BOARD CONTEXT | SHIFT: {self.shift_id}',
                '=========================================',
            ]
            self.context_lines.append(
                "Use mcp_ticket with a flat, single-field interface to manage Agile tickets. Call it with action='create', 'read', 'update', 'search', or 'comment' plus flat string arguments: item_type, item_id, field_name, field_value, parent_id, query. Perform atomic updates by calling mcp_ticket once per field you want to change (for example, call it twice to update both 'status' and 'priority')."
            )
            statuses = PFCItemStatus.objects.all()
            self.context_lines.append(
                f'Ticket status values IN ORDER by ("id", "name") are: '
                f'{[(status.pk, status.name) for status in statuses]}'
            )
        identity_type_id = self.identity_disc.identity_type_id
        shift_id = self.shift_id

        match shift_id:
            case Shift.SIFTING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            sifting_pm(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            bidding_worker(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
            case Shift.PRE_PLANNING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            pre_planning_pm(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            sifting_worker(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
            case Shift.PLANNING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            planning_pm(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            sifting_worker(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
            case Shift.EXECUTING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            executing_pm(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            executing_worker(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
            case Shift.POST_EXECUTION:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            post_execution_pm(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            bidding_worker(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
            case Shift.SLEEPING:
                match identity_type_id:
                    case IdentityType.PM:
                        self.context_lines.append(
                            sleeping_pm(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
                            )
                        )
                    case IdentityType.WORKER:
                        self.context_lines.append(
                            sleeping_worker(
                                self.identity_disc,
                                self.environment_id,
                                self.turn_number,
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
