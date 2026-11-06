import unittest
from decimal import Decimal

from backend.app.review.sm2 import SM2State, calculate_next_state


class SM2Tests(unittest.TestCase):
    def test_first_success_starts_one_day_interval(self) -> None:
        result = calculate_next_state(SM2State(0, Decimal("2.500"), 0), 4)

        self.assertEqual(result, SM2State(1, Decimal("2.500"), 1))

    def test_second_success_uses_six_day_interval(self) -> None:
        result = calculate_next_state(SM2State(1, Decimal("2.600"), 1), 5)

        self.assertEqual(result, SM2State(2, Decimal("2.700"), 6))

    def test_later_interval_uses_existing_ease_factor_before_grade_update(self) -> None:
        result = calculate_next_state(SM2State(2, Decimal("2.600"), 6), 5)

        # 6 * 2.6 rounds up to 16; the grade raises EF to 2.7 for the next turn.
        self.assertEqual(result, SM2State(3, Decimal("2.700"), 16))

    def test_failed_recall_resets_sequence_without_changing_ease_factor(self) -> None:
        for quality in (0, 1, 2):
            with self.subTest(quality=quality):
                result = calculate_next_state(
                    SM2State(4, Decimal("1.700"), 28),
                    quality,
                )

                self.assertEqual(result, SM2State(0, Decimal("1.700"), 1))

    def test_quality_scores_update_ease_factor(self) -> None:
        expected = {
            3: Decimal("2.360"),
            4: Decimal("2.500"),
            5: Decimal("2.600"),
        }

        for quality, expected_factor in expected.items():
            with self.subTest(quality=quality):
                result = calculate_next_state(
                    SM2State(0, Decimal("2.500"), 0),
                    quality,
                )
                self.assertEqual(result.ease_factor, expected_factor)

    def test_ease_factor_never_falls_below_classic_minimum(self) -> None:
        result = calculate_next_state(SM2State(0, Decimal("1.350"), 0), 3)

        self.assertEqual(result.ease_factor, Decimal("1.300"))

    def test_invalid_quality_is_rejected(self) -> None:
        for quality in (-1, 6, True, 3.0):
            with self.subTest(quality=quality):
                with self.assertRaises(ValueError):
                    calculate_next_state(SM2State(0, Decimal("2.500"), 0), quality)

    def test_invalid_state_is_rejected(self) -> None:
        invalid_states = (
            SM2State(-1, Decimal("2.500"), 0),
            SM2State(0, Decimal("1.200"), 0),
            SM2State(0, Decimal("NaN"), 0),
            SM2State(0, "2.500", 0),
            SM2State(0, Decimal("1000.000"), 0),
            SM2State(0, Decimal("2.500"), -1),
            SM2State(2, Decimal("2.500"), 5),
        )

        for state in invalid_states:
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    calculate_next_state(state, 4)


if __name__ == "__main__":
    unittest.main()
