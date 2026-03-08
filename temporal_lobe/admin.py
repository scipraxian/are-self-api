from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import (
    Iteration,
    IterationDefinition,
    IterationShift,
    IterationStatus,
    Shift,
    ShiftParticipant,
)


@admin.register(IterationStatus)
class IterationStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


# ==========================================
# SHIFT CONFIGURATION
# ==========================================


class ShiftParticipantInline(admin.TabularInline):
    """Binds an Identity (Persona) to a specific Agile Shift inside the Shift view."""

    model = ShiftParticipant
    extra = 1
    raw_id_fields = ('participant',)


@admin.register(ShiftParticipant)
class ShiftParticipantAdmin(admin.ModelAdmin):
    """Standalone access to the Shift Participant link table."""

    list_display = ('id', 'shift', 'participant')
    list_filter = ('shift',)
    search_fields = ('participant__name', 'shift__name')


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('name', 'turn_limit', 'participant_count')
    search_fields = ('name',)
    inlines = [ShiftParticipantInline]

    def participant_count(self, obj):
        count = obj.shiftparticipant_set.count()
        return format_html('<b>{}</b> Personas', count)

    participant_count.short_description = 'Assigned Identities'


# ==========================================
# ITERATION DEFINITION (THE LOOP BUILDER)
# ==========================================


class IterationShiftInline(admin.TabularInline):
    """Builds the sequence of the Agile Loop inside the Definition view."""

    model = IterationShift
    extra = 1
    ordering = ('order',)
    fields = ('order', 'shift')


@admin.register(IterationShift)
class IterationShiftAdmin(admin.ModelAdmin):
    """Standalone access to the Iteration Sequence link table."""

    list_display = ('id', 'definition', 'order', 'shift')
    list_filter = ('definition', 'shift')
    ordering = ('definition', 'order')


@admin.register(IterationDefinition)
class IterationDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'shift_sequence')
    search_fields = ('name',)
    inlines = [IterationShiftInline]

    def shift_sequence(self, obj):
        """Visualizes the entire flow of the loop directly in the list view."""
        shifts = obj.iterationshift_set.select_related('shift').order_by(
            'order'
        )
        if not shifts:
            # FIX: format_html requires an arg/kwarg to be secure
            return format_html(
                '<span style="color: #ef4444;">{}</span>', 'No shifts defined'
            )

        # FIX: Use format_html_join to safely assemble the breadcrumb trail
        separator = mark_safe(' <span style="color: #64748b;">➔</span> ')
        return format_html_join(
            separator,
            '<span style="color: #38bdf8;">{}</span>:{}',
            ((p.order, p.shift.name) for p in shifts),
        )

    shift_sequence.short_description = 'Execution Sequence'


# ==========================================
# ACTIVE ITERATIONS (MISSION CONTROL)
# ==========================================


@admin.register(Iteration)
class IterationAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'definition_link',
        'status_badge',
        'current_shift_ui',
        'turn_progress',
        'modified',
    )
    list_filter = ('status', 'definition', 'created')
    search_fields = ('name', 'definition__name')
    readonly_fields = ('created', 'modified', 'delta', 'turn_progress_ui')

    # Eager load relationships to prevent N+1 query explosions
    list_select_related = (
        'status',
        'definition',
        'current_shift',
        'current_shift__shift',
    )

    fieldsets = (
        ('Temporal Identity', {'fields': ('name', 'definition', 'status')}),
        (
            'Execution State',
            {
                'fields': (
                    'current_shift',
                    'turns_consumed_in_shift',
                    'turn_progress_ui',
                ),
                'description': 'Current state of the active time loop.',
            },
        ),
        (
            'System Metronome',
            {
                'fields': ('created', 'modified', 'delta'),
                'classes': ('collapse',),
            },
        ),
    )

    def definition_link(self, obj):
        return format_html('<b>{}</b>', obj.definition.name)

    definition_link.short_description = 'Loop Blueprint'

    def current_shift_ui(self, obj):
        if not obj.current_shift:
            return '-'
        return format_html(
            '<span style="color: #a855f7;">{}</span>',
            obj.current_shift.shift.name,
        )

    current_shift_ui.short_description = 'Active Shift'

    def status_badge(self, obj):
        """Color-codes the execution state."""
        color = '#94a3b8'  # Default Grey
        name = obj.status.name.upper()

        if name == 'RUNNING':
            color = '#3b82f6'  # Blue
        elif name == 'FINISHED':
            color = '#22c55e'  # Green
        elif name == 'WAITING':
            color = '#eab308'  # Yellow
        elif name == 'ERROR':
            color = '#ef4444'  # Red
        elif name == 'CANCELLED':
            color = '#f97316'  # Orange
        elif name == 'BLOCKED BY USER':
            color = '#d946ef'  # Purple

        return format_html(
            '<span style="background: rgba(0,0,0,0.2); border-left: 3px solid {}; '
            'padding: 4px 8px; font-weight: bold; color: {}; letter-spacing: 0.05em;">{}</span>',
            color,
            color,
            name,
        )

    status_badge.short_description = 'State'

    def turn_progress(self, obj):
        """Draws a mini-progress bar showing how close the shift is to timing out."""
        if not obj.current_shift or not obj.current_shift.shift:
            return '-'

        limit = obj.current_shift.shift.turn_limit
        consumed = obj.turns_consumed_in_shift
        pct = 0

        if limit > 0:
            pct = int((consumed / limit) * 100)
            pct = min(100, pct)

        # Turns green if doing fine, orange if getting close, red if maxed out
        bar_color = '#4ade80'
        if pct >= 80:
            bar_color = '#f97316'
        if pct >= 100:
            bar_color = '#ef4444'

        return format_html(
            '<div style="width: 100px; background: #1e293b; border-radius: 4px; '
            'overflow: hidden; display: inline-block; vertical-align: middle; margin-right: 8px;'
            'border: 1px solid #334155;">'
            '<div style="width: {}%; background: {}; height: 6px;"></div>'
            '</div>'
            '<span style="font-family: monospace; font-size: 0.8rem; color: #94a3b8;">{}/{}</span>',
            pct,
            bar_color,
            consumed,
            limit,
        )

    turn_progress.short_description = 'Shift Capacity'

    def turn_progress_ui(self, obj):
        return self.turn_progress(obj)

    turn_progress_ui.short_description = 'Capacity Visualization'
