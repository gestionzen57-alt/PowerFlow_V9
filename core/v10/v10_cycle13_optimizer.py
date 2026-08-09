"""
v10_cycle13_optimizer.py — CYCLE 13 : Orchestrateur principal
C13-OPT6 : Pipeline unifié SessionFilter + NewsGuard + Slippage + ExecutionScorer + LatencyMonitor.
Doctrine : R2 | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .v10_session_filter import check_session, SessionFilterResult
from .v10_news_guard import check_news_window, NewsEvent, NewsGuardResult
from .v10_slippage_model import estimate_slippage, SlippageResult
from .v10_execution_scorer import score_execution_batch, ExecutionRecord, ExecutionScoreResult
from .v10_latency_monitor import analyze_latency, LatencyReport

CYCLE_TAG = "13"
C13_FEATURES = [
    "C13-OPT1:SessionFilter",
    "C13-OPT2:NewsGuard",
    "C13-OPT3:SlippageModel",
    "C13-OPT4:ExecutionScorer",
    "C13-OPT5:LatencyMonitor",
    "C13-OPT6:C13Orchestrator",
]


@dataclass
class C13PostprocessResult:
    cycle: str = CYCLE_TAG
    signal_allowed: bool = True
    block_reasons: list[str] = field(default_factory=list)
    session: dict = field(default_factory=dict)
    news: dict = field(default_factory=dict)
    slippage: dict = field(default_factory=dict)
    execution: dict = field(default_factory=dict)
    latency: dict = field(default_factory=dict)
    c13_features: list = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle, "signal_allowed": self.signal_allowed,
            "block_reasons": self.block_reasons, "session": self.session,
            "news": self.news, "slippage": self.slippage,
            "execution": self.execution, "latency": self.latency,
            "c13_features": self.c13_features,
        }


def run_cycle13_postprocess(
    report_dict: dict[str, Any],
    pair: str = "EURUSD",
    current_utc_dt: datetime | None = None,
    news_events: list | None = None,
    execution_records: list | None = None,
    latency_samples_ms: list[float] | None = None,
    tp_pips: float = 30.0,
    sl_pips: float = 20.0,
) -> C13PostprocessResult:
    result = C13PostprocessResult(c13_features=C13_FEATURES)
    if current_utc_dt is None:
        current_utc_dt = datetime.now(timezone.utc)
    if news_events is None:
        news_events = []
    if execution_records is None:
        execution_records = []
    if latency_samples_ms is None:
        latency_samples_ms = []

    try:
        sess: SessionFilterResult = check_session(current_utc_time=current_utc_dt.time(), pair=pair)
        result.session = sess.as_dict()
        if not sess.allowed:
            result.signal_allowed = False
            result.block_reasons.append(sess.block_reason)
    except Exception as e:
        warnings.warn(f"[C13] SessionFilter fail-open: {e}")

    try:
        news: NewsGuardResult = check_news_window(
            current_time=current_utc_dt, pair=pair,
            events=[NewsEvent(**e) if isinstance(e, dict) else e for e in news_events],
        )
        result.news = news.as_dict()
        if not news.allowed:
            result.signal_allowed = False
            result.block_reasons.append(news.blocked_by)
    except Exception as e:
        warnings.warn(f"[C13] NewsGuard fail-open: {e}")

    try:
        slip: SlippageResult = estimate_slippage(
            spread_pips=float(report_dict.get("avg_spread_pips", 1.0)),
            atr_pips=float(report_dict.get("avg_atr_pips", 20.0)),
            atr_baseline_pips=float(report_dict.get("atr_baseline_pips", 20.0)),
            tp_pips=tp_pips, sl_pips=sl_pips,
        )
        result.slippage = slip.as_dict()
    except Exception as e:
        warnings.warn(f"[C13] SlippageModel fail-open: {e}")

    try:
        recs = [ExecutionRecord(**r) if isinstance(r, dict) else r for r in execution_records]
        exec_score: ExecutionScoreResult = score_execution_batch(recs)
        result.execution = exec_score.as_dict()
    except Exception as e:
        warnings.warn(f"[C13] ExecutionScorer fail-open: {e}")

    try:
        lat: LatencyReport = analyze_latency(latency_samples_ms)
        result.latency = lat.as_dict()
    except Exception as e:
        warnings.warn(f"[C13] LatencyMonitor fail-open: {e}")

    logging.getLogger("powerflow.c13").info(
        "[C13] pair=%s allowed=%s blocks=%s exec_grade=%s lat_p95=%.1fms",
        pair, result.signal_allowed, result.block_reasons,
        result.execution.get("grade", "N/A"), result.latency.get("p95_ms", 0.0),
    )
    return result
