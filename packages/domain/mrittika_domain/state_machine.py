"""Document state machine (§37).

Kept as data, in the shared domain package, so the API service layer and any
other consumer enforce exactly the same graph. Routers must never call this
directly -- transitions are a service-layer concern (§80).
"""

from .enums import DocumentState as S

#: The only legal moves. Anything not listed here is rejected.
ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.UPLOADED: frozenset({S.QUALITY_CHECK, S.REJECTED}),
    S.QUALITY_CHECK: frozenset({S.PROCESSING, S.RESCAN_REQUIRED, S.REJECTED}),
    S.PROCESSING: frozenset({S.AI_EXTRACTED, S.REJECTED, S.RESCAN_REQUIRED}),
    S.AI_EXTRACTED: frozenset({S.NEEDS_VERIFICATION}),
    # §29 controlled reprocessing: before any human has worked a document, its
    # extraction may be re-run (e.g. after an extractor fix). It re-enters at
    # PROCESSING and can only come back out through NEEDS_VERIFICATION, so this
    # can never be used to skip verification. The service layer refuses it
    # once a verifier has corrected or accepted anything.
    S.NEEDS_VERIFICATION: frozenset({S.UNDER_VERIFICATION, S.PROCESSING}),
    # A verifier may send a document back for a new scan rather than guess.
    S.UNDER_VERIFICATION: frozenset(
        {S.VERIFIED, S.NEEDS_VERIFICATION, S.RESCAN_REQUIRED}
    ),
    S.VERIFIED: frozenset({S.PENDING_APPROVAL}),
    # The tehsildar may approve, return to the verifier, demand a rescan,
    # or reject outright (§32).
    S.PENDING_APPROVAL: frozenset(
        {S.APPROVED, S.UNDER_VERIFICATION, S.RESCAN_REQUIRED, S.REJECTED}
    ),
    S.APPROVED: frozenset({S.ARCHIVED}),
    S.REJECTED: frozenset({S.ARCHIVED}),
    S.RESCAN_REQUIRED: frozenset({S.UPLOADED, S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
}

#: States in which a citizen may see the derived record at all (§17).
CITIZEN_VISIBLE_STATES: frozenset[S] = frozenset({S.APPROVED})

#: Terminal states -- no further transition is possible.
TERMINAL_STATES: frozenset[S] = frozenset({S.ARCHIVED})


class IllegalTransitionError(ValueError):
    """Raised when a caller attempts a transition the graph forbids."""

    def __init__(self, current: S, target: S) -> None:
        allowed = sorted(t.value for t in ALLOWED_TRANSITIONS.get(current, frozenset()))
        super().__init__(
            f"Illegal document transition {current.value} -> {target.value}. "
            f"Allowed from {current.value}: {allowed or '(terminal state)'}"
        )
        self.current = current
        self.target = target


def can_transition(current: S, target: S) -> bool:
    """True if `current -> target` is a legal move."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: S, target: S) -> None:
    """Raise IllegalTransitionError unless `current -> target` is legal.

    Call this in the service layer before persisting any state change.
    """
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
