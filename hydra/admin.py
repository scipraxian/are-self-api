from django.contrib import admin
from django.utils.html import format_html
from .models import (HydraExecutable, HydraSwitch, HydraEnvironment,
                     HydraSpellOutcomeConfig, HydraSpellbook, HydraSpell,
                     HydraSpellOutcome, HydraSpawnStatus, HydraSpawn,
                     HydraHeadStatus, HydraHead, HydraResult)

# --- Inlines ---


class HydraSwitchInline(admin.TabularInline):
    model = HydraSwitch
    extra = 1
    fields = ('name', 'flag', 'value')


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


@admin.register(HydraEnvironment)
class HydraEnvironmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'project_environment', 'created')
    list_filter = ('project_environment',)
    filter_horizontal = ('executables',)
    search_fields = ('name',)


@admin.register(HydraSpell)
class HydraSpellAdmin(admin.ModelAdmin):
    list_display = ('name', 'executable')
    list_filter = ('executable',)
    search_fields = ('name',)
    filter_horizontal = ('active_switches',)
    save_as = True


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')
    search_fields = ('name',)
    filter_horizontal = ('spells', 'outcomes')
    save_as = True


@admin.register(HydraSpawn)
class HydraSpawnAdmin(admin.ModelAdmin):
    list_display = ('id', 'spellbook', 'environment', 'status_display',
                    'created')
    list_filter = ('status', 'environment', 'spellbook')
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
    list_display = ('id', 'spawn', 'spell', 'status_display', 'result_code',
                    'created')
    list_filter = ('status', 'spell', 'spawn')
    readonly_fields = ('celery_task_id', 'spell_log_formatted',
                       'execution_log_formatted', 'created', 'modified')
    exclude = ('spell_log', 'execution_log')
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
    list_display = ('name', 'created')


@admin.register(HydraSpellOutcome)
class HydraSpellOutcomeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'outcome_config')
