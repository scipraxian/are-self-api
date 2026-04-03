from django.contrib import admin

from .models import (
    ContextVariable,
    Executable,
    ExecutableArgument,
    ExecutableArgumentAssignment,
    ExecutableSupplementaryFileOrPath,
    ExecutableSwitch,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)


@admin.register(ExecutableSwitch)
class ExecutableSwitchAdmin(admin.ModelAdmin):
    list_display = ('name', 'flag', 'value', 'id')
    search_fields = ('name', 'flag')
    ordering = ('flag',)
    list_editable = ('flag', 'value')


@admin.register(ExecutableArgument)
class ExecutableArgumentAdmin(admin.ModelAdmin):
    list_display = ('name', 'argument')
    search_fields = (
        'name',
        'argument',
    )


class ArgumentAssignmentInline(admin.TabularInline):
    """Allows ordering arguments directly on the Executable page."""

    model = ExecutableArgumentAssignment
    extra = 1
    autocomplete_fields = [
        'argument'
    ]  # Requires search_fields on ArgumentAdmin
    ordering = ('order',)


class SupplementaryFileInline(admin.TabularInline):
    """Manages output paths/manifests associated with the tool."""

    model = ExecutableSupplementaryFileOrPath
    extra = 1


@admin.register(Executable)
class ExecutableAdmin(admin.ModelAdmin):
    list_display = ('name', 'executable_short', 'working_path', 'switch_count')
    search_fields = ('name', 'executable')
    list_filter = ('working_path',)

    # The Power User Interface
    inlines = [ArgumentAssignmentInline, SupplementaryFileInline]
    filter_horizontal = ('switches',)

    fieldsets = (
        ('Identity', {'fields': ('name', 'description')}),
        (
            'Execution',
            {
                'fields': ('internal', 'executable', 'working_path', 'log'),
                'description': 'Absolute paths to the binary, CWD, and log output.',
            },
        ),
        (
            'Flags & Options',
            {
                'fields': ('switches',),
                'description': 'Global flags (unordered) that always apply.',
            },
        ),
    )

    def executable_short(self, obj):
        """Truncate long paths for the list view."""
        return (
            (obj.executable[:50] + '..')
            if len(obj.executable) > 50
            else obj.executable
        )

    executable_short.short_description = 'Executable Path'

    def switch_count(self, obj):
        return obj.switches.count()

    switch_count.short_description = '# Switches'


@admin.register(ProjectEnvironmentType)
class ProjectEnvironmentTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(ProjectEnvironmentStatus)
class ProjectEnvironmentStatusAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(ProjectEnvironmentContextKey)
class ProjectEnvironmentContextKeyAdmin(admin.ModelAdmin):
    """Registered to allow inline autocomplete."""

    list_display = ('name',)
    search_fields = ('name',)


class EnvironmentContextInline(admin.TabularInline):
    model = ContextVariable
    extra = 1
    autocomplete_fields = ['key']  # Enables the search/add widget


@admin.register(ProjectEnvironment)
class ProjectEnvironmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'status', 'variable_count')
    list_filter = ('type', 'status')
    inlines = [EnvironmentContextInline]

    def variable_count(self, obj):
        return obj.contexts.count()

    variable_count.short_description = '# Variables'
