class Stimulus:
    """
    A biological signal representation passed from Thalamus to Frontal Lobe.
    """

    def __init__(self, source, description, context_data=None):
        self.source = source
        self.description = description
        self.context_data = context_data or {}

    def __str__(self):
        return f"Stimulus({self.source}): {self.description}"
