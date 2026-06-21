
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict

from .models import PouringRecord, Severity, IssueType
from .tracker import TrackingResult


HISTORY_DIRNAME = ".inspection_history"


@dataclass
class WeeklySnapshot:
    snapshot_date: str
    project_name: str
    date_range_start: str = ""
    date_range_end: str = ""
    total_records: int = 0
    ok_records: int = 0
    issue_records: int = 0
    pass_rate: float = 0.0
    total_issues: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    consistency_conflicts: int = 0
    unmatched_manifests: int = 0
    issue_type_distribution: Dict[str, int] = field(default_factory=dict)
    building_stats: Dict[str, Dict] = field(default_factory=dict)
    supervisor_stats: Dict[str, Dict] = field(default_factory=dict)
    role_stats: Dict[str, int] = field(default_factory=dict)
    tracking_available: bool = False
    tracking_resolved: int = 0
    tracking_still_open: int = 0
    tracking_new: int = 0
    tracking_false_resolved: int = 0
    tracking_close_rate: float = 0.0


@dataclass
class TrendResult:
    snapshots: List[WeeklySnapshot]
    weeks: List[str]
    pass_rate_trend: List[float]
    total_issues_trend: List[int]
    close_rate_trend: List[float]
    issue_type_trends: Dict[str, List[int]]
    building_issue_trends: Dict[str, List[int]]

    @property
    def weeks_count(self) -> int:
        return len(self.weeks)


class HistoryStore:
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()
        self.history_dir = self.project_dir / HISTORY_DIRNAME
        self.weekly_dir = self.history_dir / "weekly"
        self.tracking_dir = self.history_dir / "tracking"

    def _ensure_dirs(self):
        self.weekly_dir.mkdir(parents=True, exist_ok=True)
        self.tracking_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_snapshot(
        records: List[PouringRecord],
        date_range: Tuple[Optional[datetime], Optional[datetime]] = None,
        tracking_result: Optional[TrackingResult] = None,
    ) -> WeeklySnapshot:
        total = len(records)
        ok = sum(1 for r in records if not r.has_issues)
        total_issues = sum(len(r.issues) for r in records)
        critical = sum(1 for r in records for i in r.issues if i.severity == Severity.CRITICAL)
        high = sum(1 for r in records for i in r.issues if i.severity == Severity.HIGH)
        medium = sum(1 for r in records for i in r.issues if i.severity == Severity.MEDIUM)
        low = sum(1 for r in records for i in r.issues if i.severity == Severity.LOW)
        consistency = sum(1 for r in records if r.consistency_issues)
        unmatched = sum(1 for r in records if r.manifest_unmatched)

        issue_type_dist: Dict[str, int] = {}
        for r in records:
            for issue in r.issues:
                key = issue.issue_type.value
                issue_type_dist[key] = issue_type_dist.get(key, 0) + 1

        building_stats: Dict[str, Dict] = {}
        for r in records:
            b = r.building or "未识别楼栋"
            if b not in building_stats:
                building_stats[b] = {"total": 0, "issues": 0, "issue_count": 0, "critical": 0}
            building_stats[b]["total"] += 1
            if r.has_issues:
                building_stats[b]["issues"] += 1
            building_stats[b]["issue_count"] += len(r.issues)
            building_stats[b]["critical"] += len(r.critical_issues)

        supervisor_stats: Dict[str, Dict] = {}
        for r in records:
            s = r.supervisor or "未填写"
            if s not in supervisor_stats:
                supervisor_stats[s] = {"total": 0, "issues": 0, "issue_count": 0}
            supervisor_stats[s]["total"] += 1
            if r.has_issues:
                supervisor_stats[s]["issues"] += 1
            supervisor_stats[s]["issue_count"] += len(r.issues)

        role_stats: Dict[str, int] = {}
        for r in records:
            for issue in r.issues:
                role = issue.responsible or "未指定"
                role_stats[role] = role_stats.get(role, 0) + 1

        snap = WeeklySnapshot(
            snapshot_date=datetime.now().strftime("%Y-%m-%d"),
            project_name="",
            date_range_start=date_range[0].strftime("%Y-%m-%d") if date_range and date_range[0] else "",
            date_range_end=date_range[1].strftime("%Y-%m-%d") if date_range and date_range[1] else "",
            total_records=total,
            ok_records=ok,
            issue_records=total - ok,
            pass_rate=(ok / total * 100) if total else 0.0,
            total_issues=total_issues,
            critical_issues=critical,
            high_issues=high,
            medium_issues=medium,
            low_issues=low,
            consistency_conflicts=consistency,
            unmatched_manifests=unmatched,
            issue_type_distribution=issue_type_dist,
            building_stats=building_stats,
            supervisor_stats=supervisor_stats,
            role_stats=role_stats,
        )

        if tracking_result is not None:
            snap.tracking_available = True
            snap.tracking_resolved = len(tracking_result.resolved) + len(tracking_result.historical_only_closed)
            snap.tracking_still_open = len(tracking_result.still_open)
            snap.tracking_new = len(tracking_result.new_issues)
            snap.tracking_false_resolved = len(tracking_result.false_resolved)
            hist_total = tracking_result.total_historical
            snap.tracking_close_rate = (snap.tracking_resolved / hist_total * 100) if hist_total else 0.0

        return snap

    def save_weekly(self, snapshot: WeeklySnapshot) -> str:
        self._ensure_dirs()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"weekly_{timestamp}.json"
        filepath = self.weekly_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(snapshot), f, ensure_ascii=False, indent=2)
        return str(filepath)

    def save_tracking(self, result: TrackingResult, snapshot: WeeklySnapshot = None) -> str:
        self._ensure_dirs()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tracking_{timestamp}.json"
        filepath = self.tracking_dir / filename
        data = {
            "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
            "total_historical": result.total_historical,
            "total_current": result.total_current,
            "resolved": len(result.resolved),
            "still_open": len(result.still_open),
            "new_issues": len(result.new_issues),
            "false_resolved": len(result.false_resolved),
            "historical_only_closed": len(result.historical_only_closed),
            "close_rate": ((len(result.resolved) + len(result.historical_only_closed))
                           / result.total_historical * 100) if result.total_historical else 0.0,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(filepath)

    def load_recent_snapshots(self, limit: int = 8) -> List[WeeklySnapshot]:
        if not self.weekly_dir.exists():
            return []
        files = sorted(self.weekly_dir.glob("weekly_*.json"), reverse=True)[:limit]
        files = list(reversed(files))
        result = []
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                snap = WeeklySnapshot(**data)
                result.append(snap)
            except Exception:
                continue
        return result

    def compute_trend(self, limit: int = 8) -> TrendResult:
        snapshots = self.load_recent_snapshots(limit)
        if not snapshots:
            return TrendResult(
                snapshots=[], weeks=[], pass_rate_trend=[],
                total_issues_trend=[], close_rate_trend=[],
                issue_type_trends={}, building_issue_trends={},
            )

        weeks = []
        pass_rates = []
        issue_counts = []
        close_rates = []

        all_issue_types = set()
        all_buildings = set()
        for s in snapshots:
            all_issue_types.update(s.issue_type_distribution.keys())
            all_buildings.update(s.building_stats.keys())

        issue_type_trends: Dict[str, List[int]] = {t: [] for t in sorted(all_issue_types)}
        building_trends: Dict[str, List[int]] = {b: [] for b in sorted(all_buildings)}

        for s in snapshots:
            label = s.snapshot_date
            if s.date_range_start and s.date_range_end:
                label = f"{s.date_range_start}~{s.date_range_end[-5:]}"
            weeks.append(label)
            pass_rates.append(round(s.pass_rate, 1))
            issue_counts.append(s.total_issues)
            close_rates.append(round(s.tracking_close_rate, 1) if s.tracking_available else None)
            for t in issue_type_trends:
                issue_type_trends[t].append(s.issue_type_distribution.get(t, 0))
            for b in building_trends:
                building_trends[b].append(s.building_stats.get(b, {}).get("issue_count", 0))

        return TrendResult(
            snapshots=snapshots,
            weeks=weeks,
            pass_rate_trend=pass_rates,
            total_issues_trend=issue_counts,
            close_rate_trend=close_rates,
            issue_type_trends=issue_type_trends,
            building_issue_trends=building_trends,
        )

    @staticmethod
    def format_trend_report(trend: TrendResult, project_name: str = "") -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("混凝土浇筑旁站检查  历史趋势报告")
        lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if project_name:
            lines.append(f"项目名称：{project_name}")
        if trend.weeks_count == 0:
            lines.append("-" * 72)
            lines.append("⚠️  暂无历史数据，请先运行 weekly 命令生成周报")
            lines.append("=" * 72)
            return "\n".join(lines)

        lines.append(f"数据周数：{trend.weeks_count} 周")
        lines.append("=" * 72)
        lines.append("")

        lines.append("【一、资料合格率 & 问题总数趋势】")
        lines.append("-" * 72)
        header = f"  {'周次':<22} {'合格率':<10} {'问题总数':<10}"
        if any(cr is not None for cr in trend.close_rate_trend):
            header += f" {'整改关闭率':<10}"
        lines.append(header)
        for idx, wk in enumerate(trend.weeks):
            pr = f"{trend.pass_rate_trend[idx]}%"
            ic = str(trend.total_issues_trend[idx])
            row = f"  {wk:<22} {pr:<10} {ic:<10}"
            if any(cr is not None for cr in trend.close_rate_trend):
                cr = trend.close_rate_trend[idx]
                row += f" {f'{cr}%' if cr is not None else '-':<10}"
            lines.append(row)
        lines.append("")

        if trend.issue_type_trends:
            lines.append("【二、问题类型变化（按数量降序显示TOP8）】")
            lines.append("-" * 72)
            sorted_types = sorted(
                trend.issue_type_trends.items(),
                key=lambda x: -sum(x[1])
            )[:8]
            header = f"  {'问题类型':<18}"
            for wk in trend.weeks:
                header += f" {wk[-5:]:<8}"
            lines.append(header)
            for itype, counts in sorted_types:
                row = f"  {itype:<18}"
                for c in counts:
                    row += f" {c:<8}"
                row += f" (累计{sum(counts)})"
                lines.append(row)
            lines.append("")

        if trend.building_issue_trends:
            lines.append("【三、楼栋问题变化】")
            lines.append("-" * 72)
            header = f"  {'楼栋':<12}"
            for wk in trend.weeks:
                header += f" {wk[-5:]:<8}"
            lines.append(header)
            sorted_bld = sorted(
                trend.building_issue_trends.items(),
                key=lambda x: -sum(x[1])
            )
            for bld, counts in sorted_bld:
                row = f"  {bld:<12}"
                for c in counts:
                    row += f" {c:<8}"
                row += f" (累计{sum(counts)})"
                lines.append(row)
            lines.append("")

        lines.append("=" * 72)
        return "\n".join(lines)

    @staticmethod
    def save_trend_csv(trend: TrendResult, output_dir: str, project_name: str = "") -> str:
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"趋势报告_{timestamp}.csv"
        filepath = out_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)

                writer.writerow(["混凝土浇筑旁站 历史趋势报告"])
                writer.writerow([f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
                if project_name:
                    writer.writerow([f"项目名称：{project_name}"])
                writer.writerow([])

                writer.writerow(["一、合格率 & 问题总数趋势"])
                header1 = ["周次", "合格率(%)", "问题总数"]
                if any(cr is not None for cr in trend.close_rate_trend):
                    header1.append("整改关闭率(%)")
                writer.writerow(header1)
                for idx, wk in enumerate(trend.weeks):
                    row = [wk, trend.pass_rate_trend[idx], trend.total_issues_trend[idx]]
                    if any(cr is not None for cr in trend.close_rate_trend):
                        cr = trend.close_rate_trend[idx]
                        row.append(cr if cr is not None else "")
                    writer.writerow(row)
                writer.writerow([])

                if trend.issue_type_trends:
                    writer.writerow(["二、问题类型变化"])
                    header2 = ["问题类型"] + trend.weeks + ["累计"]
                    writer.writerow(header2)
                    sorted_types = sorted(
                        trend.issue_type_trends.items(),
                        key=lambda x: -sum(x[1])
                    )
                    for itype, counts in sorted_types:
                        writer.writerow([itype] + counts + [sum(counts)])
                    writer.writerow([])

                if trend.building_issue_trends:
                    writer.writerow(["三、楼栋问题变化"])
                    header3 = ["楼栋"] + trend.weeks + ["累计"]
                    writer.writerow(header3)
                    sorted_bld = sorted(
                        trend.building_issue_trends.items(),
                        key=lambda x: -sum(x[1])
                    )
                    for bld, counts in sorted_bld:
                        writer.writerow([bld] + counts + [sum(counts)])

        except Exception as e:
            print(f"趋势CSV导出失败：{e}")
            return ""
        return str(filepath)


def get_history_store(project_dir: str) -> HistoryStore:
    return HistoryStore(project_dir)
