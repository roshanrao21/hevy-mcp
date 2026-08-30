from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PageRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=5, ge=1, le=100)


class RoutineSet(BaseModel):
    type: Literal["normal", "warmup", "dropset", "failure"] = "normal"
    weight_kg: float | None = Field(default=None, ge=0, le=1500)
    reps: int | None = Field(default=None, ge=0, le=1000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    distance_meters: float | None = Field(default=None, ge=0, le=1_000_000)
    rep_range: dict[str, int] | None = None


class RoutineExercise(BaseModel):
    exercise_template_id: str = Field(min_length=1, max_length=128)
    superset_id: int | None = Field(default=None, ge=0)
    rest_seconds: int | None = Field(default=None, ge=0, le=7200)
    notes: str | None = Field(default=None, max_length=2000)
    sets: list[RoutineSet] = Field(default_factory=list, max_length=100)


class RoutineInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    folder_id: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)
    exercises: list[RoutineExercise] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return " ".join(value.split())


class WorkoutSet(BaseModel):
    type: Literal["normal", "warmup", "dropset", "failure"] = "normal"
    weight_kg: float | None = Field(default=None, ge=0, le=1500)
    reps: int | None = Field(default=None, ge=0, le=1000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    distance_meters: float | None = Field(default=None, ge=0, le=1_000_000)
    rpe: float | None = Field(default=None, ge=1, le=10)


class WorkoutExercise(BaseModel):
    exercise_template_id: str = Field(min_length=1, max_length=128)
    superset_id: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    sets: list[WorkoutSet] = Field(default_factory=list, max_length=100)


class WorkoutInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_time: datetime
    end_time: datetime
    description: str | None = Field(default=None, max_length=4000)
    exercises: list[WorkoutExercise] = Field(min_length=1, max_length=100)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: datetime, info):
        start = info.data.get("start_time")
        if start and value <= start:
            raise ValueError("end_time must be after start_time")
        return value


class ToolResult(BaseModel):
    ok: bool
    data: Any | None = None
    error: dict[str, Any] | None = None
