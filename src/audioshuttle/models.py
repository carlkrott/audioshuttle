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
    track_count: int = 0
    master_volume: float = Field(default=0.75, ge=0.0, le=1.0)
    master_pan: float = Field(default=0.0, ge=-1.0, le=1.0)

    model_config = {"populate_by_name": True}


class FXState(BaseModel):
    """State of an FX plugin on a track."""

    track_number: int = Field(ge=1)
    fx_index: int = Field(ge=0)
    name: str = ""
    bypassed: bool = False
    params: dict[int, float] = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


class TranslationResult(BaseModel):
    """Result of translating a natural language command to a tool call."""

    success: bool
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    raw_response: Optional[str] = None
    method: str = ""  # "model" or "fallback"
    delay_ms: int = 0  # Delay before executing this command (for sequencing)
    model_config = {"populate_by_name": True}
