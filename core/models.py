import uuid
from django.db import models


class RemoteTarget(models.Model):
    """The fleet of build agents. Populated by Network Scanner or Config."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hostname = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    unc_path = models.CharField(max_length=500, help_text="Network share path e.g. \\\\DREWDESK01\\steambuild")
    agent_port = models.IntegerField(default=5005)
    
    # Status Tracking
    is_enabled = models.BooleanField(default=True)
    version = models.CharField(max_length=20, blank=True, null=True, help_text="Reported agent version")
    last_seen = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, 
        choices=[
            ('ONLINE', 'Online'),
            ('OFFLINE', 'Offline'),
            ('BUSY', 'Busy'),
            ('STORAGE_ERROR', 'Storage Error')
        ],
        default='OFFLINE'
    )
    
    # Discovery Fields
    remote_build_path = models.CharField(max_length=500, blank=True, help_text="Configured build root on the agent")
    remote_exe_path = models.CharField(max_length=500, blank=True, help_text="Located .exe path for launching")
    remote_log_path = models.CharField(max_length=500, blank=True, help_text="Configured project log path")
    is_exe_available = models.BooleanField(default=False)

    def __str__(self):
        return self.hostname


class PipelineStage(models.Model):
    """Defines a button on your dashboard."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    order_index = models.FloatField(help_text="Order in the UI (e.g. 0.5, 1.0)")
    script_filename = models.CharField(max_length=100, help_text="Filename in core/builder_engine/")
    description = models.TextField(blank=True)
    timeout_seconds = models.IntegerField(default=300)

    class Meta:
        ordering = ['order_index']

    def __str__(self):
        return f"{self.order_index}: {self.name}"


class BuildJob(models.Model):
    """A record of a specific execution run."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
        ('ABORTED', 'Aborted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stage = models.ForeignKey(PipelineStage, on_delete=models.CASCADE)
    celery_task_id = models.UUIDField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    
    # Snapshot of config used for this run
    target_environment = models.ForeignKey('environments.ProjectEnvironment', on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.stage.name} - {self.status} ({self.started_at.strftime('%H:%M')})"


class JobLog(models.Model):
    """The console output storage."""
    job = models.OneToOneField(BuildJob, on_delete=models.CASCADE, related_name='log')
    content = models.TextField(blank=True)