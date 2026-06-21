
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from .models import PouringRecord, Issue, Severity


@dataclass
class HistoricalIssue:
    record_id: str
    issue_type: str
    description: str
    building: str = ""
    position: str = ""
    strength: str = ""
    pouring_date: str = ""
    supervisor: str = ""
    severity: str = ""
    is_rectified: str = ""
    responsible_person: str = ""
    plan_date: str = ""
    actual_date: str = ""
    remark: str = ""
    source_file: str = ""


@dataclass
class TrackingResult:
    resolved: List[Tuple[HistoricalIssue, Issue]] = field(default_factory=list)
    still_open: List[Tuple[HistoricalIssue, Issue, PouringRecord]] = field(default_factory=list)
    new_issues: List[Tuple[Issue, PouringRecord]] = field(default_factory=list)
    false_resolved: List[Tuple[HistoricalIssue, Issue, PouringRecord]] = field(default_factory=list)
    historical_only_closed: List[HistoricalIssue] = field(default_factory=list)

    @property
    def total_historical(self) -> int:
        return len(self.resolved) + len(self.still_open) + len(self.false_resolved) + len(self.historical_only_closed)

    @property
    def total_current(self) -> int:
        return len(self.new_issues) + len(self.still_open) + len(self.false_resolved)


class IssueTracker:
    def __init__(self, historical_csv_path: str = None):
        self.historical_issues: Dict[str, HistoricalIssue] = {}
        if historical_csv_path:
            self.load_historical_csv(historical_csv_path)

    def load_historical_csv(self, csv_path: str) -> int:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"历史整改CSV不存在：{csv_path}")

        def _find_col(headers, keywords):
            for h in headers:
                h_clean = str(h).strip()
                for kw in keywords:
                    if kw in h_clean:
                        return h
            return None

        count = 0
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            col_record_id = _find_col(headers, ["记录编号"])
            col_issue_type = _find_col(headers, ["问题类型"])
            col_desc = _find_col(headers, ["问题详情"])
            col_building = _find_col(headers, ["楼栋"])
            col_position = _find_col(headers, ["部位"])
            col_strength = _find_col(headers, ["强度"])
            col_date = _find_col(headers, ["浇筑日期"])
            col_supervisor = _find_col(headers, ["监理员"])
            col_severity = _find_col(headers, ["严重程度"])
            col_rectified = _find_col(headers, ["是否整改"])
            col_resp = _find_col(headers, ["指定责任人", "责任人"])
            col_plan = _find_col(headers, ["计划完成日期", "计划日期"])
            col_actual = _find_col(headers, ["实际完成日期", "实际日期"])
            col_remark = _find_col(headers, ["备注"])

            for row in reader:
                record_id = row.get(col_record_id, "").strip() if col_record_id else ""
                issue_type = row.get(col_issue_type, "").strip() if col_issue_type else ""
                if not record_id or not issue_type:
                    continue
                key = f"{record_id}||{issue_type}"
                hi = HistoricalIssue(
                    record_id=record_id,
                    issue_type=issue_type,
                    description=row.get(col_desc, "") if col_desc else "",
                    building=row.get(col_building, "") if col_building else "",
                    position=row.get(col_position, "") if col_position else "",
                    strength=row.get(col_strength, "") if col_strength else "",
                    pouring_date=row.get(col_date, "") if col_date else "",
                    supervisor=row.get(col_supervisor, "") if col_supervisor else "",
                    severity=row.get(col_severity, "") if col_severity else "",
                    is_rectified=row.get(col_rectified, "").strip() if col_rectified else "",
                    responsible_person=row.get(col_resp, "").strip() if col_resp else "",
                    plan_date=row.get(col_plan, "").strip() if col_plan else "",
                    actual_date=row.get(col_actual, "").strip() if col_actual else "",
                    remark=row.get(col_remark, "").strip() if col_remark else "",
                    source_file=str(path.name),
                )
                self.historical_issues[key] = hi
                count += 1
        return count

    def compare_with_current(self, current_records: List[PouringRecord]) -> TrackingResult:
        result = TrackingResult()

        current_map: Dict[str, Tuple[Issue, PouringRecord]] = {}
        for r in current_records:
            for issue in r.issues:
                key = f"{r.record_id}||{issue.issue_type.value}"
                current_map[key] = (issue, r)

        historical_keys = set(self.historical_issues.keys())
        current_keys = set(current_map.keys())

        only_historical = historical_keys - current_keys
        both = historical_keys & current_keys
        only_current = current_keys - historical_keys

        for key in only_historical:
            hi = self.historical_issues[key]
            if self._is_marked_rectified(hi):
                result.historical_only_closed.append(hi)
            else:
                result.resolved.append((hi, None))

        for key in both:
            hi = self.historical_issues[key]
            issue, record = current_map[key]
            if self._is_marked_rectified(hi):
                result.false_resolved.append((hi, issue, record))
            else:
                result.still_open.append((hi, issue, record))

        for key in only_current:
            issue, record = current_map[key]
            result.new_issues.append((issue, record))

        result.resolved.sort(key=lambda x: (x[0].severity, x[0].record_id))
        result.still_open.sort(key=lambda x: (x[1].severity.order, x[2].record_id))
        result.new_issues.sort(key=lambda x: (x[0].severity.order, x[1].record_id))
        result.false_resolved.sort(key=lambda x: (x[1].severity.order, x[2].record_id))
        result.historical_only_closed.sort(key=lambda x: (x.severity, x.record_id))

        return result

    def _is_marked_rectified(self, hi: HistoricalIssue) -> bool:
        val = hi.is_rectified.strip().lower()
        return val in ("是", "y", "yes", "true", "1", "已整改", "已完成", "已关闭")

    def generate_tracking_report(self, result: TrackingResult, project_name: str = "") -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("混凝土浇筑旁站检查  问题跟踪周报")
        lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if project_name:
            lines.append(f"项目名称：{project_name}")
        lines.append("=" * 72)
        lines.append("")

        lines.append("【一、跟踪概览】")
        lines.append("-" * 72)
        lines.append(f"  上周问题总数：{result.total_historical}")
        lines.append(f"  本周问题总数：{result.total_current}")
        lines.append(f"  已整改关闭：{len(result.resolved)}")
        lines.append(f"  仍未整改：{len(result.still_open)}")
        lines.append(f"  本周新增：{len(result.new_issues)}")
        lines.append(f"  标记整改但仍存在：{len(result.false_resolved)}")
        lines.append(f"  已关闭（历史标记）：{len(result.historical_only_closed)}")
        if result.total_historical > 0:
            close_rate = (len(result.resolved) + len(result.historical_only_closed)) / result.total_historical * 100
            lines.append(f"  整改关闭率：{close_rate:.1f}%")
        lines.append("")

        if result.false_resolved:
            lines.append(f"【二、需核实：标记整改但仍存在的问题（{len(result.false_resolved)}项）】")
            lines.append("-" * 72)
            for idx, (hi, issue, r) in enumerate(result.false_resolved, 1):
                date_str = r.pouring_date.strftime("%Y-%m-%d") if r.pouring_date else ""
                lines.append(f"  {idx:>2}. [{issue.severity.value}] {r.building or '-'} {r.position or '-'}（{date_str}）")
                lines.append(f"      · 问题：{issue.issue_type.value}")
                lines.append(f"      · 上周标记：{hi.is_rectified}  责任人：{hi.responsible_person or '-'}")
                lines.append(f"      · 本周状态：仍存在 - {issue.description[:60]}")
            lines.append("")

        if result.still_open:
            lines.append(f"【三、持续跟踪：仍未整改的问题（{len(result.still_open)}项）】")
            lines.append("-" * 72)
            for idx, (hi, issue, r) in enumerate(result.still_open, 1):
                date_str = r.pouring_date.strftime("%Y-%m-%d") if r.pouring_date else ""
                lines.append(f"  {idx:>2}. [{issue.severity.value}] {r.building or '-'} {r.position or '-'}（{date_str}）")
                lines.append(f"      · 问题：{issue.issue_type.value}")
                lines.append(f"      · 责任人：{hi.responsible_person or '-'}  计划日期：{hi.plan_date or '-'}")
                lines.append(f"      · 详情：{issue.description[:70]}")
            lines.append("")

        if result.new_issues:
            lines.append(f"【四、本周新增问题（{len(result.new_issues)}项）】")
            lines.append("-" * 72)
            for idx, (issue, r) in enumerate(result.new_issues, 1):
                date_str = r.pouring_date.strftime("%Y-%m-%d") if r.pouring_date else ""
                lines.append(f"  {idx:>2}. [{issue.severity.value}] {r.building or '-'} {r.position or '-'}（{date_str}）")
                lines.append(f"      · 问题：{issue.issue_type.value}")
                lines.append(f"      · 详情：{issue.description[:70]}")
                if issue.suggestion:
                    lines.append(f"      · 整改建议：{issue.suggestion[:60]}")
            lines.append("")

        if result.resolved:
            lines.append(f"【五、已整改关闭（{len(result.resolved)}项）】")
            lines.append("-" * 72)
            for idx, (hi, _) in enumerate(result.resolved, 1):
                lines.append(f"  {idx:>2}. [{hi.severity}] {hi.building} {hi.position}（{hi.pouring_date}）")
                lines.append(f"      · {hi.issue_type}")
            lines.append("")

        lines.append("=" * 72)
        return "\n".join(lines)

    def save_tracking_csv(self, result: TrackingResult, output_dir: str = ".", filename: str = None) -> str:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"问题跟踪周报_{timestamp}.csv"
        filepath = out_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)

                writer.writerow(["混凝土浇筑旁站 问题跟踪周报"])
                writer.writerow([f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
                writer.writerow([])

                writer.writerow(["一、跟踪概览"])
                writer.writerow(["指标", "数值"])
                writer.writerow(["上周问题总数", result.total_historical])
                writer.writerow(["本周问题总数", result.total_current])
                writer.writerow(["已整改关闭", len(result.resolved)])
                writer.writerow(["仍未整改", len(result.still_open)])
                writer.writerow(["本周新增", len(result.new_issues)])
                writer.writerow(["标记整改但仍存在", len(result.false_resolved)])
                writer.writerow(["历史已关闭", len(result.historical_only_closed)])
                if result.total_historical > 0:
                    close_rate = (len(result.resolved) + len(result.historical_only_closed)) / result.total_historical * 100
                    writer.writerow(["整改关闭率", f"{close_rate:.1f}%"])
                writer.writerow([])

                writer.writerow(["二、标记整改但仍存在（需核实）"])
                self._write_issue_rows(writer, [
                    (issue, record, hi) for hi, issue, record in result.false_resolved
                ], include_history=True)
                writer.writerow([])

                writer.writerow(["三、仍未整改（持续跟踪）"])
                self._write_issue_rows(writer, [
                    (issue, record, hi) for hi, issue, record in result.still_open
                ], include_history=True)
                writer.writerow([])

                writer.writerow(["四、本周新增问题"])
                self._write_issue_rows(writer, [
                    (issue, record, None) for issue, record in result.new_issues
                ], include_history=True)
                writer.writerow([])

                writer.writerow(["五、已整改关闭"])
                writer.writerow(["序号", "记录编号", "楼栋", "部位", "强度等级", "浇筑日期",
                                 "问题类型", "严重程度", "问题详情", "责任人", "实际完成日期", "备注"])
                for idx, (hi, _) in enumerate(result.resolved, 1):
                    writer.writerow([idx, hi.record_id, hi.building, hi.position, hi.strength,
                                     hi.pouring_date, hi.issue_type, hi.severity, hi.description,
                                     hi.responsible_person, hi.actual_date, hi.remark])

        except Exception as e:
            print(f"跟踪CSV导出失败：{e}")
            return ""
        return str(filepath)

    def save_rolling_action_csv(self, result: TrackingResult, output_dir: str = ".",
                                filename: str = None) -> str:
        """导出与list命令完全一致的21列整改清单CSV，方便项目部滚动填写下周继续用
        包含：still_open(仍未整改) + false_resolved(假整改) + new_issues(本周新增)
        """
        from .reporter import ReportGenerator

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        merged_records: Dict[str, PouringRecord] = {}
        historical_issues_map: Dict[str, HistoricalIssue] = {}

        for hi, issue, record in result.false_resolved:
            key = f"{record.record_id}||{issue.issue_type.value}"
            historical_issues_map[key] = hi
            if record.record_id not in merged_records:
                merged_records[record.record_id] = record

        for hi, issue, record in result.still_open:
            key = f"{record.record_id}||{issue.issue_type.value}"
            historical_issues_map[key] = hi
            if record.record_id not in merged_records:
                merged_records[record.record_id] = record

        for issue, record in result.new_issues:
            if record.record_id not in merged_records:
                merged_records[record.record_id] = record

        records = list(merged_records.values())
        records.sort(key=lambda r: (r.building or "", r.pouring_date or datetime.min))

        reporter = ReportGenerator(str(out_dir))
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"滚动整改清单_{timestamp}.csv"
        return reporter.save_action_csv(records, filename=filename, historical_issues=historical_issues_map)

    def _write_issue_rows(self, writer, items, include_history=False):
        headers = ["序号", "记录编号", "楼栋", "部位", "强度等级", "浇筑日期",
                   "监理员", "问题类型", "严重程度", "问题详情", "整改建议", "责任岗位",
                   "指定责任人", "计划完成日期", "是否整改", "实际完成日期", "备注"]
        writer.writerow(headers)
        for idx, (issue, record, hi) in enumerate(items, 1):
            date_str = record.pouring_date.strftime("%Y-%m-%d") if record.pouring_date else ""
            resp = issue.responsible or ""
            sug = issue.suggestion or ""
            if hi:
                writer.writerow([
                    idx, record.record_id, record.building or "", record.position or "",
                    record.strength_grade or "", date_str, record.supervisor or "",
                    issue.issue_type.value, issue.severity.value, issue.description,
                    sug, resp,
                    hi.responsible_person, hi.plan_date, hi.is_rectified, hi.actual_date, hi.remark,
                ])
            else:
                writer.writerow([
                    idx, record.record_id, record.building or "", record.position or "",
                    record.strength_grade or "", date_str, record.supervisor or "",
                    issue.issue_type.value, issue.severity.value, issue.description,
                    sug, resp,
                    "", "", "", "", "",
                ])


def load_tracker(csv_path: str) -> IssueTracker:
    return IssueTracker(csv_path)
