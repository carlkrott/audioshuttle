"""MIDI Pattern Generator — pseudo-random patterns for different instrument roles."""

from __future__ import annotations

import random
from typing import Any


class MIDIGenerator:
    """Generate pseudo-random MIDI patterns for different instrument roles.

    Each pattern is a list of bars, where each bar is a list of step velocities (0-127).
    0 = note off, 1-127 = note velocity.
    """

    # Steps per bar for each role
    STEPS_PER_BAR: dict[str, int] = {
        "drums": 4,
        "rhythm": 8,
        "lead": 8,
        "melody": 8,
    }

    def generate(
        self,
        role: str,
        bars: int = 16,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Generate a pattern for the given role.

        Args:
            role: Instrument role — "drums", "rhythm", "lead", or "melody".
            bars: Number of bars (default 16).
            seed: Random seed for reproducibility. None = random.

        Returns:
            Dict with role, bars, pattern (bars × steps grid), seed used.
        """
        if seed is None:
            seed = random.randint(0, 2**31)

        rng = random.Random(seed)
        steps = self.STEPS_PER_BAR.get(role, 8)

        generator_map = {
            "drums": self._generate_drums,
            "rhythm": self._generate_rhythm,
            "lead": self._generate_lead,
            "melody": self._generate_melody,
        }

        gen_fn = generator_map.get(role, self._generate_rhythm)
        pattern = gen_fn(rng, bars, steps)

        return {
            "role": role,
            "bars": bars,
            "steps_per_bar": steps,
            "pattern": pattern,
            "seed": seed,
        }

    def _generate_drums(
        self, rng: random.Random, bars: int, steps: int
    ) -> list[list[int]]:
        """Drums: kick on 1,3; snare on 2,4; hi-hat with velocity variation."""
        pattern = []
        for _ in range(bars):
            bar = []
            for s in range(steps):
                velocity = 0
                if s == 0:  # kick on beat 1
                    velocity = rng.randint(100, 127)
                elif s == 2:  # snare on beat 3 (0-indexed step 2)
                    velocity = rng.randint(90, 120)
                # Hi-hat: add subtle hits on other steps with 40% probability
                if velocity == 0 and rng.random() < 0.4:
                    velocity = rng.randint(30, 70)
                bar.append(velocity)
            pattern.append(bar)
        return pattern

    def _generate_rhythm(
        self, rng: random.Random, bars: int, steps: int
    ) -> list[list[int]]:
        """Rhythm: repetitive 2-4 bar cycle, higher density."""
        # Generate a 2-bar cycle, repeat it
        cycle_len = rng.choice([2, 4])
        cycle = []
        for _ in range(cycle_len):
            bar = []
            for s in range(steps):
                # 65% density
                velocity = rng.randint(60, 110) if rng.random() < 0.65 else 0
                bar.append(velocity)
            cycle.append(bar)

        pattern = []
        for i in range(bars):
            pattern.append(cycle[i % cycle_len])
        return pattern

    def _generate_lead(
        self, rng: random.Random, bars: int, steps: int
    ) -> list[list[int]]:
        """Lead: melodic, wider intervals, ~50% density, occasional rests."""
        pattern = []
        for _ in range(bars):
            bar = []
            for s in range(steps):
                if rng.random() < 0.50:
                    velocity = rng.randint(50, 120)
                else:
                    velocity = 0
                bar.append(velocity)
            pattern.append(bar)
        return pattern

    def _generate_melody(
        self, rng: random.Random, bars: int, steps: int
    ) -> list[list[int]]:
        """Melody: scale-constrained, stepwise motion, ~60% density."""
        pattern = []
        for _ in range(bars):
            bar = []
            for s in range(steps):
                if rng.random() < 0.60:
                    # Stepwise: tend toward mid-range velocities
                    velocity = rng.randint(40, 100)
                else:
                    velocity = 0
                bar.append(velocity)
            pattern.append(bar)
        return pattern
