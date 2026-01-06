from django.db import models

class BuildProfile(models.Model):
    name = models.CharField(max_length=100, unique=True)
    headless = models.BooleanField(default=False)
    staging = models.BooleanField(default=False)
    steam = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class PipelineRun(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    profile = models.ForeignKey(BuildProfile, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, null=True)

    def duration(self):
        if self.finished_at:
            return (self.finished_at - self.created_at).total_seconds()
        return None

    def get_previous_run(self):
        return PipelineRun.objects.filter(profile=self.profile, created_at__lt=self.created_at).order_by('-created_at').first()

    def __str__(self):
        return f"Run {self.id} - {self.profile.name} ({self.status})"

class PipelineStepRun(models.Model):
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name='steps')
    step_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=PipelineRun.STATUS_CHOICES, default='PENDING')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    logs = models.TextField(blank=True)

    def duration(self):
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def get_delta(self):
        prev_run = self.pipeline_run.get_previous_run()
        if prev_run:
            prev_step = prev_run.steps.filter(step_name=self.step_name, status='SUCCESS').first()
            if prev_step and prev_step.duration() and self.duration():
                return self.duration() - prev_step.duration()
        return None

    def __str__(self):
        return f"{self.step_name} - {self.status}"
