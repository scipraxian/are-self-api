from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import (
    Iteration,
    IterationDefinition,
    IterationShift,
    IterationShiftDefinition,
    IterationShiftDefinitionParticipant,
    IterationShiftParticipant,
    IterationShiftParticipantStatus,
    IterationStatus,
    Shift,
    ShiftDefaultParticipant,
)


@admin.register(IterationShiftParticipantStatus)
class IterationShiftParticipantStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(IterationShiftParticipant)
class IterationShiftParticipantAdmin(admin.ModelAdmin):
    list_display = ('id', 'status')


@admin.register(IterationStatus)
class IterationStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


# ==========================================
# 1. MASTER TEMPLATES (SHIFTS)
# ==========================================
class ShiftDefaultParticipantInline(admin.TabularInline):
    model = ShiftDefaultParticipant
    extra = 1
    raw_id_fields = ('participant',)


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('name', 'default_turn_limit')
    search_fields = ('name',)
    inlines = [ShiftDefaultParticipantInline]


# ==========================================
# 2. BLUEPRINTS (DEFINITIONS)
# ==========================================
class IterationShiftDefinitionParticipantInline(admin.TabularInline):
    model = IterationShiftDefinitionParticipant
    extra = 1
    raw_id_fields = ('identity_disc',)


@admin.register(IterationShiftDefinition)
class IterationShiftDefinitionAdmin(admin.ModelAdmin):
    list_display = ('id', 'definition', 'order', 'shift', 'turn_limit')
    list_filter = ('definition', 'shift')
    ordering = ('definition', 'order')
    inlines = [IterationShiftDefinitionParticipantInline]


class IterationShiftDefinitionInline(admin.TabularInline):
    model = IterationShiftDefinition
    extra = 1
    ordering = ('order',)
    fields = ('order', 'shift', 'turn_limit')
    show_change_link = True


@admin.register(IterationDefinition)
class IterationDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'shift_sequence', 'genome')
    list_filter = ('genome',)
    search_fields = ('name',)
    inlines = [IterationShiftDefinitionInline]

    def shift_sequence(self, obj):
        shifts = obj.iterationshiftdefinition_set.select_related(
            'shift'
        ).order_by('order')
        if not shifts:
            return format_html(
                '<span style="color: #ef4444;">{}</span>', 'No shifts defined'
            )

        separator = mark_safe(' <span style="color: #64748b;">➔</span> ')
        return format_html_join(
            separator,
            '<span style="color: #38bdf8;">{}</span>:{}',
            ((p.order, p.shift.name) for p in shifts),
        )

    shift_sequence.short_description = 'Execution Sequence'


# ==========================================
# 3. RUNTIME (INSTANCES)
# ==========================================
class IterationShiftParticipantInline(admin.TabularInline):
    model = IterationShiftParticipant
    extra = 1
    raw_id_fields = ('iteration_participant',)


@admin.register(IterationShift)
class IterationShiftAdmin(admin.ModelAdmin):
    list_display = ('id', 'shift_iteration', 'shift', 'definition')
    list_filter = ('iteration',)
    inlines = [IterationShiftParticipantInline]


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

    list_select_related = (
        'status',
        'definition',
        'current_shift',
        'current_shift__shift',
    )

    fieldsets = (
        (
            'Temporal Identity',
            {'fields': ('name', 'definition', 'status', 'environment')},
        ),
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
        color = '#94a3b8'
        name = obj.status.name.upper()

        if name == 'RUNNING':
            color = '#3b82f6'
        elif name == 'FINISHED':
            color = '#22c55e'
        elif name == 'WAITING':
            color = '#eab308'
        elif name == 'ERROR':
            color = '#ef4444'
        elif name == 'CANCELLED':
            color = '#f97316'
        elif name == 'BLOCKED BY USER':
            color = '#d946ef'

        return format_html(
            '<span style="background: rgba(0,0,0,0.2); border-left: 3px solid {}; '
            'padding: 4px 8px; font-weight: bold; color: {}; letter-spacing: 0.05em;">{}</span>',
            color,
            color,
            name,
        )

    status_badge.short_description = 'State'

    def turn_progress(self, obj):
        if not obj.current_shift or not obj.current_shift.definition:
            return '-'

        # Note: Limit now pulls from the Definition Blueprint, not the base Shift
        limit = obj.current_shift.definition.turn_limit
        consumed = obj.turns_consumed_in_shift
        pct = 0

        if limit > 0:
            pct = int((consumed / limit) * 100)
            pct = min(100, pct)

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
