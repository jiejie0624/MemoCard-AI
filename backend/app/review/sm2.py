"""Pure SM-2 state transitions for a single flashcard review."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP


_MIN_EASE_FACTOR = Decimal("1.300")
_EASE_FACTOR_QUANTUM = Decimal("0.001")
_MAX_STORED_EASE_FACTOR = Decimal("999.999")


@dataclass(frozen=True)
class SM2State:
    """The scheduling fields needed to calculate one SM-2 review result."""

    repetition_count: int
    ease_factor: Decimal
    interval_days: int


def calculate_next_state(state: SM2State, quality: int) -> SM2State:
    """Return the next scheduling state after a grade from 0 through 5.

    The current interval is calculated from the ease factor already stored on
    the card. The grade updates the ease factor for the following review.
    """
    _validate_state(state, quality)

    if quality < 3:
        # A failed recall restarts the successful repetition sequence. The MVP
        # schedules the retry for the next day and preserves the old EF.
        return SM2State(
            repetition_count=0,
            ease_factor=state.ease_factor,
            interval_days=1,
        )

    if state.repetition_count == 0:
        next_interval = 1
    elif state.repetition_count == 1:
        next_interval = 6
    else:
        interval = Decimal(state.interval_days) * state.ease_factor
        next_interval = int(interval.to_integral_value(rounding=ROUND_CEILING))

    next_ease_factor = _updated_ease_factor(state.ease_factor, quality)
    if next_ease_factor > _MAX_STORED_EASE_FACTOR:
        raise ValueError("Updated ease factor exceeds the current database precision")

    return SM2State(
        repetition_count=state.repetition_count + 1,
        ease_factor=next_ease_factor,
        interval_days=next_interval,
    )


def _updated_ease_factor(current: Decimal, quality: int) -> Decimal:
    difference = Decimal(5 - quality)
    change = Decimal("0.1") - difference * (
        Decimal("0.08") + difference * Decimal("0.02")
    )
    updated = current + change
    return max(_MIN_EASE_FACTOR, updated).quantize(
        _EASE_FACTOR_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _validate_state(state: SM2State, quality: int) -> None:
    if type(quality) is not int or not 0 <= quality <= 5:
        raise ValueError("Quality must be an integer from 0 through 5")
    if type(state.repetition_count) is not int or state.repetition_count < 0:
        raise ValueError("Repetition count must be a non-negative integer")
    if type(state.interval_days) is not int or state.interval_days < 0:
        raise ValueError("Interval must be a non-negative integer")
    if state.repetition_count >= 2 and state.interval_days < 6:
        raise ValueError("An established repetition sequence must have an interval of at least 6 days")

    if not isinstance(state.ease_factor, Decimal):
        raise ValueError("Ease factor must be a Decimal value")
    ease_factor = state.ease_factor
    if not ease_factor.is_finite() or ease_factor < _MIN_EASE_FACTOR:
        raise ValueError("Ease factor must be finite and at least 1.3")
    if ease_factor > _MAX_STORED_EASE_FACTOR:
        raise ValueError("Ease factor exceeds the current database precision")
    try:
        stored_precision_factor = ease_factor.quantize(_EASE_FACTOR_QUANTUM)
    except InvalidOperation as error:
        raise ValueError("Ease factor must fit the database's three-decimal precision") from error
    if ease_factor != stored_precision_factor:
        raise ValueError("Ease factor must fit the database's three-decimal precision")
