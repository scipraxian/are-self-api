class ModelRegistry:
    """
    The cognitive capabilities of the Parietal Lobe.
    """
    SCOUT_LIGHT = "llama3.2:3b"
    SURGEON_HEAVY = "deepseek-coder-v2"

    @classmethod
    def get_model(cls, role):
        if role == 'scout_light':
            return cls.SCOUT_LIGHT
        elif role == 'surgeon_heavy':
            return cls.SURGEON_HEAVY
        return cls.SCOUT_LIGHT
