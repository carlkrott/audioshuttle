"""AudioShuttle data models for DAW state and OSC commands."""

from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field


class TrackState(BaseModel):
    """State of a single Reaper track."""

    track_number: int = Field(ge=1)
    name: str = ""
    volume: float = Field(default=0.75, ge=0.0, le=1.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    mute: bool = False
    solo: bool = False
    selected: bool = False

    model_config = {"populate_by_name": True}


class TransportState(BaseModel):
    """Reaper transport (playback) state."""

    playing: bool = False
    recording: bool = False
    position_seconds: float = 0.0
    tempo: float = 120.0
    time_signature: str = "4/4"

    model_config = {"populate_by_name": True}


class OSCCommand(BaseModel):
    """An OSC message to send to Reaper."""

    address: str
    args: list[float | int | str] = Field(default_factory=list)
    description: str = ""

    model_config = {"populate_by_name": True}


class CommandResult(BaseModel):
    """Result of sending an OSC command to Reaper."""

    success: bool
    address: str
    sent_value: Any = None
    reaper_feedback: Optional[Any] = None
    error: Optional[str] = None

    model_config = {"populate_by_name": True}


class DAWState(BaseModel):
    """Complete snapshot of the DAW state."""

    tracks: list[TrackState] = Field(default_factory=list)
    transport: TransportState = Field(default_factory=TransportState)
    project_name: str = ""
    timestamp: float = Field(default_factory=time.time)

    model_config = {"populate_by_name": True}
