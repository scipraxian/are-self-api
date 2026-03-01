async def begin_play(spike_id: str) -> tuple[int, str]:
    """
    The Big Bang.
    Instantly returns Success (200) to fire the first wire.
    """
    return 200, 'Graph Execution Started.'
