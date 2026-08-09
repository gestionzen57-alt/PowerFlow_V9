"""
v10_confluence_filter.py — Cycle 17
Filtre de confluence multi-source pondéré.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass
class ConfluenceVote:
    source: str
    direction: str
    weight: float


@dataclass
class ConfluenceResult:
    pair: str
    final_direction: str
    confluence_score: float
    votes_for: int
    votes_against: int
    votes_neutral: int
    approved: bool
    reason: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "direction": self.final_direction,
            "score": round(self.confluence_score, 2),
            "for": self.votes_for,
            "against": self.votes_against,
            "neutral": self.votes_neutral,
            "approved": self.approved,
            "reason": self.reason,
        }


class ConfluenceFilter:
    MIN_CONFLUENCE = 65.0
    MIN_VOTES_FOR = 3

    def evaluate(self, pair: str, direction: str, votes: List[ConfluenceVote]) -> ConfluenceResult:
        total_weight = sum(v.weight for v in votes) or 1.0
        score_for = sum(v.weight for v in votes if v.direction == direction)
        confluence = (score_for / total_weight) * 100
        votes_for = sum(1 for v in votes if v.direction == direction)
        votes_against = sum(1 for v in votes if v.direction not in (direction, "NEUTRAL"))
        votes_neutral = sum(1 for v in votes if v.direction == "NEUTRAL")
        approved = confluence >= self.MIN_CONFLUENCE and votes_for >= self.MIN_VOTES_FOR
        reason = "OK" if approved else (
            f"confluence={confluence:.1f}<{self.MIN_CONFLUENCE}" if confluence < self.MIN_CONFLUENCE
            else f"votes_for={votes_for}<{self.MIN_VOTES_FOR}"
        )
        return ConfluenceResult(
            pair=pair, final_direction=direction,
            confluence_score=confluence,
            votes_for=votes_for, votes_against=votes_against,
            votes_neutral=votes_neutral,
            approved=approved, reason=reason,
        )
