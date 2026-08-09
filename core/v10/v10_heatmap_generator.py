"""
v10_heatmap_generator.py — Cycle 14
Génère des heatmaps de performance (paire × session, paire × timeframe, etc.).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
import statistics


@dataclass
class HeatmapCell:
    row_key: str
    col_key: str
    value: float
    count: int
    win_rate: float

    def as_dict(self) -> dict:
        return {
            "row": self.row_key,
            "col": self.col_key,
            "value": round(self.value, 4),
            "count": self.count,
            "win_rate": round(self.win_rate, 4),
        }


class HeatmapGenerator:
    """
    Construit des matrices de performance sur deux dimensions quelconques.
    Axes typiques : pair × session, pair × timeframe, session × regime.
    """

    def __init__(self) -> None:
        # data[row][col] = list[(pnl, win)]
        self._data: Dict[str, Dict[str, List[Tuple[float, bool]]]] = {}

    def record(self, row: str, col: str, pnl: float, win: bool) -> None:
        self._data.setdefault(row, {}).setdefault(col, []).append((pnl, win))

    def build(self) -> List[HeatmapCell]:
        cells = []
        for row, cols in self._data.items():
            for col, entries in cols.items():
                pnls = [e[0] for e in entries]
                wins = sum(1 for e in entries if e[1])
                cells.append(
                    HeatmapCell(
                        row_key=row,
                        col_key=col,
                        value=statistics.mean(pnls),
                        count=len(entries),
                        win_rate=wins / len(entries),
                    )
                )
        return cells

    def best_cell(self) -> HeatmapCell | None:
        cells = self.build()
        return max(cells, key=lambda c: c.value) if cells else None

    def worst_cell(self) -> HeatmapCell | None:
        cells = self.build()
        return min(cells, key=lambda c: c.value) if cells else None

    def as_matrix(self) -> Dict[str, Dict[str, float]]:
        """Retourne une matrice row→col→avg_pnl pour affichage."""
        matrix: Dict[str, Dict[str, float]] = {}
        for row, cols in self._data.items():
            matrix[row] = {}
            for col, entries in cols.items():
                matrix[row][col] = round(statistics.mean(e[0] for e in entries), 4)
        return matrix

    def reset(self) -> None:
        self._data.clear()
