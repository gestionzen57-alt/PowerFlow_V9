"""
v10_streak_detector.py — Cycle 15
Détecte les séries de gains/pertes consécutives et émet des alertes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Streak:
    streak_type: str   # WIN | LOSS
    length: int
    total_pnl: float
    start_idx: int
    end_idx: int

    def as_dict(self) -> dict:
        return {
            "type": self.streak_type,
            "length": self.length,
            "total_pnl": round(self.total_pnl, 4),
            "start": self.start_idx,
            "end": self.end_idx,
        }


class StreakDetector:
    """
    Suit les séries win/loss et alerte au-delà des seuils configurés.
    """

    WARN_LOSS_STREAK = 3
    ALERT_LOSS_STREAK = 5
    WARN_WIN_STREAK = 6

    def __init__(self) -> None:
        self._results: List[tuple] = []  # (win: bool, pnl: float)

    def record(self, win: bool, pnl: float) -> None:
        self._results.append((win, pnl))

    def current_streak(self) -> Optional[Streak]:
        if not self._results:
            return None
        last_win, _ = self._results[-1]
        streak_type = "WIN" if last_win else "LOSS"
        count = 0
        total = 0.0
        for i in range(len(self._results) - 1, -1, -1):
            w, pnl = self._results[i]
            if w == last_win:
                count += 1
                total += pnl
            else:
                break
        start = len(self._results) - count
        return Streak(
            streak_type=streak_type,
            length=count,
            total_pnl=total,
            start_idx=start,
            end_idx=len(self._results) - 1,
        )

    def streak_alert(self) -> Optional[str]:
        s = self.current_streak()
        if s is None:
            return None
        if s.streak_type == "LOSS":
            if s.length >= self.ALERT_LOSS_STREAK:
                return f"ALERT: {s.length} pertes consécutives"
            if s.length >= self.WARN_LOSS_STREAK:
                return f"WARN: {s.length} pertes consécutives"
        elif s.streak_type == "WIN" and s.length >= self.WARN_WIN_STREAK:
            return f"INFO: {s.length} gains consécutifs — vérifier suroptimisation"
        return None

    def all_streaks(self) -> List[Streak]:
        if not self._results:
            return []
        streaks = []
        start = 0
        current_type = self._results[0][0]
        current_pnl = 0.0
        for i, (w, pnl) in enumerate(self._results):
            if w == current_type:
                current_pnl += pnl
            else:
                streaks.append(Streak(
                    streak_type="WIN" if current_type else "LOSS",
                    length=i - start,
                    total_pnl=current_pnl,
                    start_idx=start,
                    end_idx=i - 1,
                ))
                start = i
                current_type = w
                current_pnl = pnl
        streaks.append(Streak(
            streak_type="WIN" if current_type else "LOSS",
            length=len(self._results) - start,
            total_pnl=current_pnl,
            start_idx=start,
            end_idx=len(self._results) - 1,
        ))
        return streaks

    def reset(self) -> None:
        self._results.clear()
