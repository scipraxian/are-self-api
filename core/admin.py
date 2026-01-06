from django.contrib import admin
from .models import RemoteTarget, PipelineStage, BuildJob, JobLog
from environments.models import ProjectEnvironment

@admin.register(ProjectEnvironment)
class EnvAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'project_root')

@admin.register(PipelineStage)
class StageAdmin(admin.ModelAdmin):
    list_display = ('order_index', 'name', 'script_filename')

@admin.register(BuildJob)
class JobAdmin(admin.ModelAdmin):
    list_display = ('stage', 'status', 'started_at', 'exit_code')
    list_filter = ('status', 'stage')

admin.site.register(RemoteTarget)
admin.site.register(JobLog)