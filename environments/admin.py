from django.contrib import admin
from .models import (
    ProjectEnvironment,
    TalosExecutable,
    TalosExecutableSwitch,
    TalosExecutableSupplementaryFileOrPath
)

@admin.register(ProjectEnvironment)
class ProjectEnvironmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'project_name', 'is_active', 'agent_port')
    list_filter = ('is_active',)
    search_fields = ('name', 'project_name')

@admin.register(TalosExecutableSwitch)
class TalosExecutableSwitchAdmin(admin.ModelAdmin):
    list_display = ('name', 'flag', 'value', 'id')
    search_fields = ('name', 'flag')
    ordering = ('flag',)

class SupplementaryFileInline(admin.TabularInline):
    model = TalosExecutableSupplementaryFileOrPath
    extra = 1

@admin.register(TalosExecutable)
class TalosExecutableAdmin(admin.ModelAdmin):
    list_display = ('name', 'working_path', 'executable')
    search_fields = ('name', 'executable')
    # This makes selecting default switches for the tool much easier
    filter_horizontal = ('switches',)
    inlines = [SupplementaryFileInline]
