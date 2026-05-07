"""AMD GPU VRAM monitoring via sysfs."""

from __future__ import annotations


def get_gpu_vram(card_index: int = 1) -> dict[str, float | int]:
    """Read VRAM usage from AMD GPU sysfs.

    Args:
        card_index: DRM card index (0=iGPU, 1=discrete GPU on this system).
    """
    base = f"/sys/class/drm/card{card_index}/device"
    try:
        with open(f"{base}/mem_info_vram_total") as f:
            total = int(f.read().strip())
        with open(f"{base}/mem_info_vram_used") as f:
            used = int(f.read().strip())
        return {
            "vram_total_mb": total // (1024 * 1024),
            "vram_used_mb": used // (1024 * 1024),
            "vram_used_pct": round(used / total * 100, 1) if total > 0 else 0.0,
        }
    except (FileNotFoundError, ZeroDivisionError):
        return {"vram_total_mb": 0, "vram_used_mb": 0, "vram_used_pct": 0.0}
