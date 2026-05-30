from noxus.constants import MAX_TUNING_ITERATIONS


def test_max_tuning_iterations_equals_two():
    assert MAX_TUNING_ITERATIONS == 2, (
        "Invariant Violation: MAX_TUNING_ITERATIONS must be exactly 2."
    )
