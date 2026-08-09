"""
v10_latency_monitor.py — CYCLE 13 : Latency Monitor
C13-OPT5 : SLA p95 < 200ms, p99 < 500ms, détection spikes.
Doctrine : R2 | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import Any

SLA_P95_MS: float = 200.0
SLA_P99_MS: float = 500.0
ANOMALY_MULTIPLIER: float = 3.0


@dataclass
class LatencyReport:
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    sla_p95_ok: bool = True
    sla_p99_ok: bool = True
    anomalies: list[float] = field(default_factory=list)
    alert: bool = False
    alert_reason: str = ""
    samples: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"p50_ms": self.p50_ms, "p95_ms": self.p95_ms, "p99_ms": self.p99_ms,
                "max_ms": self.max_ms, "mean_ms": self.mean_ms,
                "sla_p95_ok": self.sla_p95_ok, "sla_p99_ok": self.sla_p99_ok,
                "anomalies_count": len(self.anomalies), "alert": self.alert, "alert_reason": self.alert_reason}


def analyze_latency(samples_ms: list[float]) -> LatencyReport:
    report = LatencyReport(samples=len(samples_ms))
    if not samples_ms:
        return report
    try:
        import statistics
        s = sorted(samples_ms)
        n = len(s)
        report.p50_ms  = round(s[int(n * 0.50)], 2)
        report.p95_ms  = round(s[min(n-1, int(n * 0.95))], 2)
        report.p99_ms  = round(s[min(n-1, int(n * 0.99))], 2)
        report.max_ms  = round(s[-1], 2)
        report.mean_ms = round(statistics.mean(s), 2)
        median = statistics.median(s)
        report.anomalies = [v for v in s if v > median * ANOMALY_MULTIPLIER]
        report.sla_p95_ok = report.p95_ms <= SLA_P95_MS
        report.sla_p99_ok = report.p99_ms <= SLA_P99_MS
        if not report.sla_p95_ok:
            report.alert = True
            report.alert_reason = f"SLA_P95_BREACH p95={report.p95_ms}ms>{SLA_P95_MS}ms"
        elif not report.sla_p99_ok:
            report.alert = True
            report.alert_reason = f"SLA_P99_BREACH p99={report.p99_ms}ms>{SLA_P99_MS}ms"
        elif len(report.anomalies) > max(1, n * 0.05):
            report.alert = True
            report.alert_reason = f"SPIKE_RATE anomalies={len(report.anomalies)}/{n}"
    except Exception as e:
        warnings.warn(f"[C13] LatencyMonitor error (fail-open): {e}")
    return report
