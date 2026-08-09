"""
v10_report_exporter.py — Cycle 14
Exporte les rapports de performance en JSON, CSV et texte structuré.
"""
from __future__ import annotations
import json
import csv
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class ReportSection:
    title: str
    data: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceReport:
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cycle: str = "C14"
    version: str = "v10"
    sections: List[ReportSection] = field(default_factory=list)

    def add_section(self, section: ReportSection) -> None:
        self.sections.append(section)

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "cycle": self.cycle,
            "version": self.version,
            "sections": [
                {
                    "title": s.title,
                    "metadata": s.metadata,
                    "rows": s.data,
                }
                for s in self.sections
            ],
        }


class ReportExporter:
    """
    Sérialise un PerformanceReport en JSON, CSV ou texte lisible.
    """

    @staticmethod
    def to_json(report: PerformanceReport, indent: int = 2) -> str:
        return json.dumps(report.as_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def to_csv(report: PerformanceReport, section_title: Optional[str] = None) -> str:
        sections = report.sections
        if section_title:
            sections = [s for s in sections if s.title == section_title]
        if not sections:
            return ""
        rows = []
        for sec in sections:
            rows.extend(sec.data)
        if not rows:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    @staticmethod
    def to_text(report: PerformanceReport) -> str:
        lines = [
            f"=== PowerFlow V10 Performance Report ===",
            f"Generated : {report.generated_at}",
            f"Cycle     : {report.cycle}  |  Version : {report.version}",
            "",
        ]
        for sec in report.sections:
            lines.append(f"--- {sec.title} ---")
            if sec.metadata:
                for k, v in sec.metadata.items():
                    lines.append(f"  {k}: {v}")
            for row in sec.data:
                lines.append("  " + "  |  ".join(f"{k}={v}" for k, v in row.items()))
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def save_json(report: PerformanceReport, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ReportExporter.to_json(report))

    @staticmethod
    def save_text(report: PerformanceReport, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ReportExporter.to_text(report))
