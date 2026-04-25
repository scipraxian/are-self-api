from django.apps import AppConfig


class FrontalLobeConfig(AppConfig):
    name = 'frontal_lobe'

    def ready(self):
        # Register the ReasoningTurn post_save receiver that materializes
        # ReasoningTurnDigest side-cars. Import for side-effect only.
        from frontal_lobe import signals  # noqa: F401
