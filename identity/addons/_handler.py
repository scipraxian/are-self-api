# identity/addons/handler.py
class IdentityAddonHandler:
    # Phase hooks (1:1 with IdentityAddonPhase, absorbs addon(turn) functions)
    def on_identify(self, turn):
        return []

    def on_context(self, turn):
        return []

    def on_history(self, turn):
        return []

    def on_terminal(self, turn):
        return []

    # Tool lifecycle hooks (new — what parietal_lobe will call)
    def on_tool_pre(self, session, mechanics):
        return None  # str = fizzle

    def on_tool_post(self, session, mechanics, result):
        return None
