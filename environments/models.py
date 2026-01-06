import uuid
from django.db import models

class ProjectEnvironment(models.Model):
    """Configuration for where the build is running (e.g., Main Desktop vs Laptop)."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, help_text="e.g., Mike Desktop 2024")
    
    # Paths
    project_root = models.CharField(max_length=500, help_text="Path to .uproject folder")
    engine_root = models.CharField(max_length=500, help_text="Path to UE_5.6 folder")
    build_root = models.CharField(max_length=500, help_text="Path to BUILD output")
    project_name = models.CharField(max_length=100, help_text="The EXE Prefix (e.g., HSHVacancy)")
    staging_dir = models.CharField(max_length=500, blank=True, null=True, help_text="Path to Staging output")
    
    agent_port = models.IntegerField(default=5005, help_text="Port the agent is listening on")
    is_active = models.BooleanField(default=False, help_text="Only one build environment can be active at a time.")

    def __str__(self):
        return f"{self.name} [{'ACTIVE' if self.is_active else 'OFF'}]"

    def save(self, *args, **kwargs):
        # Auto-populate defaults if missing
        if not self.build_root:
            self.build_root = self.DEFAULT_BUILD_ROOT
        if not self.project_name:
            self.project_name = self.DEFAULT_PROJECT_NAME
            
        # Singleton logic: If this is active, deactivate others
        if self.is_active:
            ProjectEnvironment.objects.exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)
