from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from hevy_mcp.models import RoutineInput, WorkoutInput


def test_routine_rejects_empty_exercises():
    with pytest.raises(ValidationError):
        RoutineInput(title="Push", exercises=[])


def test_workout_rejects_end_before_start():
    start = datetime.now(UTC)
    with pytest.raises(ValidationError):
        WorkoutInput(
            title="Bad workout",
            start_time=start,
            end_time=start - timedelta(minutes=1),
            exercises=[{"exercise_template_id": "abc", "sets": []}],
        )
