class ModelRegistry:
    """The cognitive capabilities registry of the Parietal Lobe.

    This registry defines the available AI models and their corresponding
    identifiers used throughout the system.
    """

    # Model Integer Constants
    SCOUT_LIGHT = 1  # llama3.2:3b
    COMMANDER = 2  # gemma3:27b

    _MODEL_MAP = {
        SCOUT_LIGHT: "llama3.2:3b",
        COMMANDER: "gemma3:27b",
    }

    @classmethod
    def get_model(cls, role_id: int | str) -> str:
        """Returns the string model name for a given role ID.

        Args:
          role_id: The integer ID or string name of the model role.

        Returns:
          The string identifier for the model (e.g., 'gemma3:27b'). Defaults
          to 'llama3.2:3b' if the ID is not found.
        """
        if isinstance(role_id, str):
            if role_id == 'scout_light':
                role_id = cls.SCOUT_LIGHT
            elif role_id == 'commander':
                role_id = cls.COMMANDER
            else:
                return cls._MODEL_MAP[cls.SCOUT_LIGHT]

        return cls._MODEL_MAP.get(role_id, cls._MODEL_MAP[cls.SCOUT_LIGHT])
