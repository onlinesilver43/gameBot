from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StateEvidence:
    attack: int = 0
    prepare: int = 0
    battle: int = 0


class StateHysteresis:
    """Tracks a stable state based on evidence and per-state enter/exit windows.

    This does NOT drive clicks; it's an observer to validate state classification.
    """

    def __init__(self) -> None:
        self.current = "scan"
        self._seen = {"attack": 0, "prepare": 0, "battle": 0}
        self._absent = {"attack": 0, "prepare": 0, "battle": 0}

        # enter hysteresis frames
        self.k_enter = {"attack": 2, "prepare": 2, "battle": 3}
        # exit hysteresis frames
        self.m_exit = {"attack": 2, "prepare": 3, "battle": 6}

    def update(self, ev: StateEvidence) -> str:
        present = {
            "attack": ev.attack > 0,
            "prepare": ev.prepare > 0,
            "battle": ev.battle > 0,
        }
        # exclusivity: battle wins over others; prepare wins over attack
        if present["battle"]:
            present["prepare"] = False
            present["attack"] = False
        elif present["prepare"]:
            present["attack"] = False

        for k, p in present.items():
            if p:
                self._seen[k] += 1
                self._absent[k] = 0
            else:
                self._absent[k] += 1
                self._seen[k] = 0

        # state transitions driven by hysteresis only for the observer
        # enter rules
        for st in ("battle", "prepare", "attack"):
            if self._seen[st] >= self.k_enter[st]:
                self.current = st
                return self.current

        # exit rules from current
        cur = self.current
        if cur in self._absent and self._absent[cur] >= self.m_exit[cur]:
            self.current = "scan"
        return self.current

