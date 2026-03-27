# import os
# from unittest.mock import MagicMock
# from identity.addons import agile_addon as agile_module
# from identity.addons.agile_addon import agile_addon
# from identity.models import IdentityType
# from prefrontal_cortex.models import PFCItemStatus
# from temporal_lobe.models import Shift

# os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

# class _FakeStatus:
#     def __init__(self, pk, name):
#         self.pk = pk
#         self.name = name

# class _StatusManager:
#     def all(self):
#         return [
#             _FakeStatus(pk=PFCItemStatus.BACKLOG, name='Backlog'),
#         ]

# class _FakeDisc:
#     def __init__(self, id, identity_type_id):
#         self.id = id
#         self.identity_type_id = identity_type_id

# class _FakeParticipant:
#     def __init__(self, shift_id, iteration_shift=None):
#         self.shift_id = shift_id
#         self.iteration_shift = iteration_shift

# class _FakeSession:
#     def __init__(self, participant=None, identity_disc=None):
#         self.participant = participant
#         self.identity_disc = identity_disc

# class _FakeTurn:
#     def __init__(self, session=None):
#         self.session = session

# def test_agile_addon_empty_on_missing_context():
#     """When no disc or reasoning turn is provided, addon returns empty list."""
#     # Current source returns [] if anything is missing
#     assert agile_addon(None) == []
    
#     turn = _FakeTurn(session=_FakeSession(participant=None, identity_disc=None))
#     assert agile_addon(turn) == []

# def test_agile_addon_preview_mode_without_shift(monkeypatch):
#     """With a disc but no shift_id, addon reports no assignment."""
#     # Mock the disc search
#     monkeypatch.setattr(
#         agile_module,
#         '_get_locked_ticket',
#         lambda disc_id: (None, None, None)
#     )

#     disc = _FakeDisc(id='fake-disc-id', identity_type_id=IdentityType.PM)
#     participant = _FakeParticipant(shift_id=None)
#     session = _FakeSession(participant=participant, identity_disc=disc)
#     turn = _FakeTurn(session=session)

#     result = agile_addon(turn)
    
#     assert len(result) == 1
#     assert 'You have no active assignments' in result[0]['content']

# def test_agile_addon_sifting_pm_context_for_pm(monkeypatch):
#     """
#     For a PM in the SIFTING shift, the addon should emit
#     Agile board context with DoR guidance and environment info.
#     """
#     # Mock the disc search to return a fake ticket
#     fake_ticket_json = '{"name": "Test Ticket"}'
#     monkeypatch.setattr(
#         agile_module,
#         '_get_locked_ticket',
#         lambda disc_id: ('STORY', 'ticket-123', fake_ticket_json)
#     )

#     disc = _FakeDisc(id='fake-disc-id', identity_type_id=IdentityType.PM)
#     participant = _FakeParticipant(shift_id=Shift.SIFTING)
#     session = _FakeSession(participant=participant, identity_disc=disc)
#     turn = _FakeTurn(session=session)

#     result = agile_addon(turn)

#     assert len(result) == 1
#     prompt = result[0]['content']
    
#     # Header & content checks
#     assert 'AGILE SHIFT ASSIGNMENT' in prompt
#     assert 'PM' in prompt
#     assert 'TICKET: ticket-123' in prompt
#     assert 'Definition of Ready (DoR)' in prompt
#     assert 'Test Ticket' in prompt
