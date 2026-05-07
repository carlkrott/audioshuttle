"""Live integration test for Phase 2 MCP tools. Requires Reaper running."""

import time
import sys

from audioshuttle.config import Settings
from audioshuttle.server import create_server


def main() -> None:
    print("=" * 60)
    print("  AudioShuttle — Phase 2 Live Integration Test")
    print("=" * 60)
    print()

    settings = Settings()
    server = create_server(settings)

    # Access the bridge directly for state checks
    # We need to get the bridge from the server closure — use call_tool instead
    import asyncio

    passed = 0
    failed = 0
    total = 0

    def run_tool(name: str, args: dict = None) -> dict:
        """Call an MCP tool by name."""
        return asyncio.run(server.call_tool(name, args or {}))

    def test(name: str, tool: str, args: dict, check_fn) -> None:
        nonlocal passed, failed, total
        total += 1
        print(f"  [{total:2d}] {name}...", end=" ", flush=True)
        try:
            result = run_tool(tool, args)
            # FastMCP returns CallToolResult with structured_content or content list
            import json
            data = None

            # Try structured_content first (fastmcp v2+)
            if hasattr(result, 'structured_content') and result.structured_content:
                data = result.structured_content
            # Try content list with TextContent
            elif hasattr(result, 'content') and result.content:
                for item in result.content:
                    if hasattr(item, 'text'):
                        data = json.loads(item.text)
                        break
            # Fallback
            elif isinstance(result, list) and len(result) > 0:
                data = json.loads(result[0].text)
            elif isinstance(result, dict):
                data = result

            if data is None:
                data = {"raw": str(result)}

            ok, detail = check_fn(data)
            if ok:
                print(f"✓ PASS  {detail}")
                passed += 1
            else:
                print(f"✗ FAIL  {detail}")
                print(f"       Response: {data}")
                failed += 1
        except Exception as e:
            print(f"✗ ERROR  {e}")
            failed += 1

    # ── Test 1: Get initial state ──────────────────────────────
    print("── Initial State ──")
    test(
        "Get track count",
        "get_track_count",
        {},
        lambda d: (d.get("track_count", 0) > 0, f"track_count={d.get('track_count')}"),
    )

    # ── Test 2: Transport Seek ─────────────────────────────────
    print("\n── Transport Seek ──")
    test(
        "Seek to 10.0 seconds",
        "transport_seek",
        {"position_seconds": 10.0},
        lambda d: (d.get("success") is True, f"success={d.get('success')}, pos={d.get('position_seconds')}"),
    )

    time.sleep(0.5)

    test(
        "Verify position updated",
        "get_transport",
        {},
        lambda d: (abs(d.get("position_seconds", 0) - 10.0) < 1.0,
                   f"position={d.get('position_seconds', 0):.1f}s (expect ~10.0)"),
    )

    # ── Test 3: Master Volume ──────────────────────────────────
    print("\n── Master Control ──")
    test(
        "Set master volume to 0.5",
        "set_master_volume",
        {"volume": 0.5},
        lambda d: (d.get("success") is True, f"volume={d.get('volume')}"),
    )

    time.sleep(0.3)

    test(
        "Set master pan to -0.25 (slight left)",
        "set_master_pan",
        {"pan": -0.25},
        lambda d: (d.get("success") is True, f"pan={d.get('pan')}"),
    )

    time.sleep(0.5)

    test(
        "Verify master state in DAW state",
        "get_daw_state",
        {},
        lambda d: (
            d.get("master_volume") is not None and d.get("master_pan") is not None,
            f"master_volume={d.get('master_volume')}, master_pan={d.get('master_pan')}"
        ),
    )

    # ── Test 4: FX Parameter Control ───────────────────────────
    print("\n── FX Control ──")
    test(
        "Set track 1 FX 0 param 0 to 0.75",
        "set_fx_param",
        {"track": 1, "fx": 0, "param": 0, "value": 0.75},
        lambda d: (d.get("success") is True, f"value={d.get('value')}"),
    )

    time.sleep(0.3)

    test(
        "Bypass track 1 FX 0",
        "fx_bypass",
        {"track": 1, "fx": 0, "bypass": True},
        lambda d: (d.get("success") is True, f"bypassed={d.get('bypassed')}"),
    )

    time.sleep(0.3)

    test(
        "Re-enable track 1 FX 0",
        "fx_bypass",
        {"track": 1, "fx": 0, "bypass": False},
        lambda d: (d.get("success") is True, f"bypassed={d.get('bypassed')}"),
    )

    # ── Test 5: Action Triggering ──────────────────────────────
    print("\n── Action Triggering ──")
    test(
        "Trigger action 1013 (Transport: Stop)",
        "trigger_action",
        {"command_id": 1013},
        lambda d: (d.get("success") is True, f"action_id={d.get('action_id')}"),
    )

    time.sleep(0.3)

    # ── Test 6: Track Arm ──────────────────────────────────────
    print("\n── Track Arm ──")
    test(
        "Arm track 1 for recording",
        "set_track_arm",
        {"track": 1, "arm": True},
        lambda d: (d.get("success") is True, f"armed={d.get('armed')}"),
    )

    time.sleep(0.5)

    test(
        "Disarm track 1",
        "set_track_arm",
        {"track": 1, "arm": False},
        lambda d: (d.get("success") is True, f"armed={d.get('armed')}"),
    )

    # ── Test 7: Toggles ───────────────────────────────────────
    print("\n── Toggles ──")
    test(
        "Toggle repeat ON",
        "toggle_repeat",
        {},
        lambda d: (d.get("success") is True, f"toggled={d.get('toggled')}"),
    )

    time.sleep(0.3)

    test(
        "Toggle repeat OFF (restore)",
        "toggle_repeat",
        {},
        lambda d: (d.get("success") is True, f"toggled={d.get('toggled')}"),
    )

    time.sleep(0.3)

    test(
        "Toggle metronome ON",
        "toggle_metronome",
        {},
        lambda d: (d.get("success") is True, f"toggled={d.get('toggled')}"),
    )

    time.sleep(0.3)

    test(
        "Toggle metronome OFF (restore)",
        "toggle_metronome",
        {},
        lambda d: (d.get("success") is True, f"toggled={d.get('toggled')}"),
    )

    # ── Test 8: Validation (should fail gracefully) ────────────
    print("\n── Validation ──")
    test(
        "Reject invalid seek position (-5)",
        "transport_seek",
        {"position_seconds": -5.0},
        lambda d: (d.get("success") is False, f"error={d.get('error', '')[:50]}"),
    )

    test(
        "Reject invalid action ID (0)",
        "trigger_action",
        {"command_id": 0},
        lambda d: (d.get("success") is False, f"error={d.get('error', '')[:50]}"),
    )

    # ── Cleanup: restore master to center ──────────────────────
    print("\n── Cleanup ──")
    run_tool("set_master_pan", {"pan": 0.0})
    run_tool("transport_seek", {"position_seconds": 0.0})
    print("  Master pan reset to center, position reset to start.")

    # ── Summary ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  ✓ ALL TESTS PASSED")
    else:
        print(f"  ✗ {failed} TESTS FAILED")
    print("=" * 60)

    # Close the bridge
    # The bridge is in a closure — we can't easily close it
    # It's daemon threads so they'll die with the process
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
