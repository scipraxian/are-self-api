from django.contrib import admin
from django.utils.html import format_html
from .models import (HydraExecutable, HydraSwitch, HydraEnvironment,
                     HydraSpellOutcomeConfig, HydraSpellbook, HydraSpell,
                     HydraSpawnStatus, HydraSpawn, HydraHeadStatus, HydraHead,
                     HydraResult, HydraOutcomeAction)

# --- Inlines ---


class HydraSwitchInline(admin.TabularInline):
    model = HydraSwitch
    extra = 1
    fields = ('name', 'flag', 'value')


class HydraSpellOutcomeConfigInline(admin.TabularInline):
    model = HydraSpellOutcomeConfig
    extra = 1
    fields = ('name', 'action', 'source_path_template', 'dest_path_template',
              'must_exist')


class HydraSpellInline(admin.TabularInline):
    model = HydraSpellbook.spells.through
    extra = 1
    verbose_name = "Spell in Book"
    verbose_name_plural = "Spells in Book"


class HydraHeadInline(admin.TabularInline):
    model = HydraHead
    extra = 0
    readonly_fields = ('spell', 'status_display', 'result_code', 'created')
    fields = ('spell', 'status_display', 'result_code', 'created')
    can_delete = False
    show_change_link = True

    def status_display(self, obj):
        if not obj.status:
            return "-"
        colors = {
            'Success': '#28a745',
            'Failed': '#dc3545',
            'Running': '#007bff',
            'Pending': '#ffc107',
            'Created': '#6c757d'
        }
        color = colors.get(obj.status.name, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color,
            obj.status.name)

    status_display.short_description = 'Status'


# --- Admins ---


@admin.register(HydraExecutable)
class HydraExecutableAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'path_template', 'created')
    search_fields = ('name', 'slug')
    inlines = [HydraSwitchInline]
    list_per_page = 20


@admin.register(HydraSwitch)
class HydraSwitchAdmin(admin.ModelAdmin):
    list_display = ('name', 'flag', 'value', 'executable')
    list_filter = ('executable',)
    search_fields = ('name', 'flag')
    list_select_related = ('executable',)


@admin.register(HydraEnvironment)
class HydraEnvironmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'project_environment', 'created')
    list_filter = ('project_environment',)
    filter_horizontal = ('executables',)
    search_fields = ('name',)


@admin.register(HydraSpell)
class HydraSpellAdmin(admin.ModelAdmin):
    list_display = ('order', 'name', 'executable', 'switch_count',
                    'outcome_count', 'in_spellbooks', 'created')
    list_filter = ('executable', 'created')
    search_fields = ('name', 'executable__name', 'executable__slug')
    filter_horizontal = ('active_switches',)
    list_select_related = ('executable',)
    inlines = [HydraSpellOutcomeConfigInline]
    save_as = True

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'active_switches', 'outcome_configs', 'hydraspellbook_set')

    def switch_count(self, obj):
        return obj.active_switches.count()

    switch_count.short_description = 'Switches'

    def outcome_count(self, obj):
        return obj.outcome_configs.count()

    outcome_count.short_description = 'Outcomes'

    def in_spellbooks(self, obj):
        return ", ".join([sb.name for sb in obj.hydraspellbook_set.all()])

    in_spellbooks.short_description = 'In Spellbooks'


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'spell_count', 'created')
    search_fields = ('name',)
    filter_horizontal = ('spells',)
    save_as = True

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('spells')

    def spell_count(self, obj):
        return obj.spells.count()

    spell_count.short_description = 'Spells'


@admin.register(HydraSpawn)
class HydraSpawnAdmin(admin.ModelAdmin):
    list_display = ('id', 'spellbook', 'environment', 'status_display',
                    'created')
    list_filter = ('status', 'environment', 'spellbook')
    list_select_related = ('spellbook', 'environment', 'status')
    readonly_fields = ('created', 'modified', 'context_data_formatted')
    inlines = [HydraHeadInline]
    date_hierarchy = 'created'
    ordering = ('-created',)

    def status_display(self, obj):
        if not obj.status:
            return "-"
        colors = {
            'Success': '#28a745',
            'Failed': '#dc3545',
            'Running': '#007bff',
            'Pending': '#ffc107',
            'Created': '#6c757d'
        }
        color = colors.get(obj.status.name, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color,
            obj.status.name)

    status_display.short_description = 'Status'

    def context_data_formatted(self, obj):
        content = obj.context_data or "{}"
        return format_html(
            '<pre style="background: #f4f4f4; padding: 10px; border-radius: 4px; font-family: monospace;">{}</pre>',
            content)

    context_data_formatted.short_description = 'Context Data (JSON)'


@admin.register(HydraHead)
class HydraHeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'spellbook_name', 'spawn', 'spell', 'status_display',
                    'result_code', 'created')
    list_filter = ('status', 'spell', 'spawn')
    list_select_related = ('spawn', 'spell', 'status', 'spawn__spellbook')
    readonly_fields = ('celery_task_id', 'spell_log_formatted',
                       'execution_log_formatted', 'created', 'modified')
    exclude = ('spell_log', 'execution_log')
    date_hierarchy = 'created'
    ordering = ('-created',)

    def spellbook_name(self, obj):
        return obj.spawn.spellbook.name

    spellbook_name.short_description = 'Spellbook'

    def status_display(self, obj):
        if not obj.status:
            return "-"
        colors = {
            'Success': '#28a745',
            'Failed': '#dc3545',
            'Running': '#007bff',
            'Pending': '#ffc107',
            'Created': '#6c757d'
        }
        color = colors.get(obj.status.name, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color,
            obj.status.name)

    status_display.short_description = 'Status'

    def spell_log_formatted(self, obj):
        log_content = obj.spell_log or "No logs available."
        return format_html(
            '<pre style="background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 5px; '
            'max-height: 500px; overflow: auto; font-family: Consolas, monospace; font-size: 12px; line-height: 1.5;">'
            '{}</pre>', log_content)

    spell_log_formatted.short_description = 'Spell Log (Stdout/Stderr)'

    def execution_log_formatted(self, obj):
        log_content = obj.execution_log or "No system logs."
        return format_html(
            '<pre style="background: #252526; color: #9cdcfe; padding: 15px; border-radius: 5px; '
            'max-height: 300px; overflow: auto; font-family: Consolas, monospace; font-size: 12px; line-height: 1.5; '
            'border-left: 4px solid #007acc;">'
            '{}</pre>', log_content)

    execution_log_formatted.short_description = 'Execution Log (System Notes)'


@admin.register(HydraSpawnStatus, HydraHeadStatus)
class HydraStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ('id',)


@admin.register(HydraResult)
class HydraResultAdmin(admin.ModelAdmin):
    list_display = ('head', 'spell', 'report', 'created')
    readonly_fields = ('created', 'modified')


@admin.register(HydraSpellOutcomeConfig)
class HydraSpellOutcomeConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'spell', 'action', 'source_path_template',
                    'created')
    list_filter = ('action', 'spell', 'created')
    list_select_related = ('spell', 'action')
    search_fields = ('name', 'source_path_template', 'dest_path_template')


@admin.register(HydraOutcomeAction)
class HydraOutcomeActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ('id',)
