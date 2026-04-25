"""Verification tests for identity/addons/handlers/.

Scope: confirm each handler class (a) imports cleanly, (b) is a proper
IdentityAddonHandler subclass, (c) returns a list from its phase method
when called with a guarded-empty input (no turn / no session).

Focus additionally gets substantive coverage for its tool-lifecycle hooks:
on_tool_pre (fizzle semantics) and on_tool_post (Focus/XP ledger semantics),
including max_focus cap, 0 floor, and focus_yield/xp_yield overrides from
tool_result objects.

These tests are pure unit tests — no DB, no fixtures — so they run even when
the heavier CommonFixturesAPITestCase suite has fixture-discovery issues.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from identity.addons._handler import IdentityAddonHandler
from identity.addons.handlers import (
    Agile,
    Deadline,
    Focus,
    Hippocampus_,
    IdentityInfo,
    NormalChat,
    Prompt,
    RiverOfSix,
    Telemetry,
    YourMove,
)


ALL_HANDLERS = [
    Agile,
    Deadline,
    Focus,
    Hippocampus_,
    IdentityInfo,
    NormalChat,
    Prompt,
    RiverOfSix,
    Telemetry,
    YourMove,
]

# Which phase method each handler implements — used for smoke tests.
HANDLER_PHASE_METHOD = {
    Agile: 'on_context',
    Deadline: 'on_context',
    Focus: 'on_context',
    Hippocampus_: 'on_context',
    IdentityInfo: 'on_identify',
    NormalChat: 'on_history',
    Prompt: 'on_terminal',
    RiverOfSix: 'on_history',
    Telemetry: 'on_context',
    YourMove: 'on_terminal',
}


class TestHandlerSubclassing(TestCase):
    """Each handler is a concrete IdentityAddonHandler subclass."""

    def test_all_handlers_inherit_base(self):
        for cls in ALL_HANDLERS:
            with self.subTest(handler=cls.__name__):
                self.assertTrue(
                    issubclass(cls, IdentityAddonHandler),
                    f'{cls.__name__} must inherit IdentityAddonHandler',
                )

    def test_all_handlers_instantiable(self):
        for cls in ALL_HANDLERS:
            with self.subTest(handler=cls.__name__):
                instance = cls()
                self.assertIsInstance(instance, IdentityAddonHandler)


class TestHandlerPhaseMethodSmoke(TestCase):
    """Each handler's phase method handles None-turn gracefully.

    The dispatcher only invokes a handler's phase method when the disc has
    that addon attached, so the handlers assume a real session in the happy
    path. What we CAN cheaply verify without DB state is the None-guard:
    passing `None` for the turn must not explode, and must return a list.

    Full happy-path coverage (with DB and real ReasoningSession state) lives
    in the integration suites that exercise each addon end-to-end.
    """

    def test_none_turn_handled_where_guarded(self):
        """Handlers that guard `not turn` should not explode on None."""
        # Deadline returns a preview block for None turn; others return [].
        # IdentityInfo does NOT guard None at entry (it touches
        # turn.session.identity_disc first) — it's deliberately excluded.
        guarded = [
            Agile,
            Deadline,
            Focus,
            Hippocampus_,
            NormalChat,
            Prompt,
            RiverOfSix,
            Telemetry,
            YourMove,
        ]
        for cls in guarded:
            with self.subTest(handler=cls.__name__):
                method = getattr(cls(), HANDLER_PHASE_METHOD[cls])
                result = method(None)
                self.assertIsInstance(result, list)


class TestFocusToolPre(TestCase):
    """on_tool_pre: fizzle semantics (no DB)."""

    def _session(self, current_focus=5):
        # SimpleNamespace works because on_tool_pre only reads attributes.
        return SimpleNamespace(current_focus=current_focus)

    def _mechanics(self, focus_modifier):
        return SimpleNamespace(focus_modifier=focus_modifier)

    def test_synthesis_tool_does_not_fizzle(self):
        """focus_modifier >= 0 is a synthesis tool — always allowed."""
        handler = Focus()
        self.assertIsNone(
            handler.on_tool_pre(self._session(0), self._mechanics(+2))
        )
        self.assertIsNone(
            handler.on_tool_pre(self._session(0), self._mechanics(0))
        )

    def test_sufficient_focus_does_not_fizzle(self):
        """Cost <= current_focus → no fizzle."""
        handler = Focus()
        self.assertIsNone(
            handler.on_tool_pre(self._session(10), self._mechanics(-5))
        )
        self.assertIsNone(
            handler.on_tool_pre(self._session(5), self._mechanics(-5))
        )

    def test_insufficient_focus_fizzles(self):
        """Cost > current_focus → fizzle message returned."""
        handler = Focus()
        msg = handler.on_tool_pre(self._session(2), self._mechanics(-5))
        self.assertIsNotNone(msg)
        self.assertIn('SYSTEM OVERRIDE', msg)
        self.assertIn('Effector Fizzled', msg)
        self.assertIn('Requires 5', msg)
        self.assertIn('only have 2', msg)

    def test_none_mechanics_does_not_fizzle(self):
        """Tool with no ToolUseType → treated as cost=0 → no fizzle."""
        handler = Focus()
        self.assertIsNone(handler.on_tool_pre(self._session(0), None))


class TestFocusToolPost(TestCase):
    """on_tool_post: Focus/XP ledger semantics (no DB)."""

    def _session(self, current_focus=5, max_focus=10, total_xp=0):
        session = MagicMock()
        session.current_focus = current_focus
        session.max_focus = max_focus
        session.total_xp = total_xp
        return session

    def _mechanics(self, focus_modifier, xp_reward):
        return SimpleNamespace(
            focus_modifier=focus_modifier, xp_reward=xp_reward
        )

    def test_normal_delta_applied(self):
        session = self._session(current_focus=5, total_xp=0)
        Focus().on_tool_post(session, self._mechanics(+1, 10), result='ok')
        self.assertEqual(session.current_focus, 6)
        self.assertEqual(session.total_xp, 10)
        session.save.assert_called_once_with(
            update_fields=['current_focus', 'total_xp']
        )

    def test_focus_capped_at_max(self):
        """current_focus + focus_mod > max_focus → clamped to max_focus."""
        session = self._session(current_focus=9, max_focus=10)
        Focus().on_tool_post(session, self._mechanics(+5, 0), result='ok')
        self.assertEqual(session.current_focus, 10)

    def test_focus_floored_at_zero(self):
        """current_focus + focus_mod < 0 → clamped to 0."""
        session = self._session(current_focus=2, max_focus=10)
        Focus().on_tool_post(session, self._mechanics(-10, 0), result='ok')
        self.assertEqual(session.current_focus, 0)

    def test_focus_yield_overrides_mechanics(self):
        """tool_result.focus_yield supersedes mechanics.focus_modifier."""
        session = self._session(current_focus=5, max_focus=10)
        result = SimpleNamespace(focus_yield=+3)
        Focus().on_tool_post(
            session, self._mechanics(-5, 0), result=result
        )
        # Ignored mechanics=-5, used yield=+3 instead → 5+3=8.
        self.assertEqual(session.current_focus, 8)

    def test_xp_yield_overrides_mechanics(self):
        session = self._session(total_xp=100)
        result = SimpleNamespace(xp_yield=25)
        Focus().on_tool_post(
            session, self._mechanics(0, 10), result=result
        )
        self.assertEqual(session.total_xp, 125)

    def test_none_mechanics_treated_as_zero(self):
        """Tool with no ToolUseType → no change to focus or xp."""
        session = self._session(current_focus=7, total_xp=50)
        Focus().on_tool_post(session, None, result='ok')
        self.assertEqual(session.current_focus, 7)
        self.assertEqual(session.total_xp, 50)


class TestFocusOnContext(TestCase):
    """Basic sanity for on_context — full coverage lives in the existing
    parietal_lobe integration tests; this just confirms the method returns
    the expected shape when called."""

    def test_no_turn_returns_empty(self):
        self.assertEqual(Focus().on_context(None), [])

    def test_returns_system_message_shape(self):
        disc = MagicMock(level=1, total_xp=0)
        session = MagicMock(
            identity_disc=disc,
            current_focus=5,
            max_focus=10,
        )
        turn = MagicMock(session=session, turn_number=1)
        turn.apply_efficiency_bonus.return_value = (True, '')
        blocks = Focus().on_context(turn)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['role'], 'system')
        self.assertIn('Focus Pool', blocks[0]['content'])
