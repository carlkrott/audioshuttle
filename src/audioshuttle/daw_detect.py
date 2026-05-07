"""DAW process detection via pgrep."""

from __future__ import annotations

import subprocess
from typing import Any


def detect_daw() -> dict[str, Any]:
    """Detect running DAWs on the local system.

    Returns dict with per-DAW running status and a 'detected' field
    naming the first running DAW (prefers Reaper if both running).
    """
    results: dict[str, Any] = {}
    daw_processes = [("reaper", "reaper"), ("ardour", "ardour-7.5")]

    for name, pattern in daw_processes:
        try:
            r = subprocess.run(
                ["pgrep", "-c", "-x", pattern],
                capture_output=True,
                text=True,
                timeout=2,
            )
            results[name] = {"running": r.returncode == 0}
        except Exception:
            results[name] = {"running": False}

    # Determine detected DAW (prefer Reaper)
    if results.get("reaper", {}).get("running", False):
        results["detected"] = "reaper"
    elif results.get("ardour", {}).get("running", False):
        results["detected"] = "ardour"
    else:
        results["detected"] = "none"

    return results
