from datetime import datetime, timedelta
from typing import List, Optional

from .models import (
    PouringRecord,
    Issue,
    IssueType,
    Severity,
    PhotoRecord,
)


class RecordValidator:
    REQUIRED_FIELDS = [
        ("position", IssueType.MISSING_POSITION, Severity.CRITICAL, "浇筑部位"),
        ("strength_grade", IssueType.MISSING_STRENGTH, Severity.CRITICAL, "强度等级"),
        ("slump", IssueType.MISSING_SLUMP, Severity.HIGH, "坍落度"),
        ("sample_count", IssueType.MISSING_SAMPLE_COUNT, Severity.HIGH, "试块组数"),
    ]

    def __init__(self, min_photo_count: int = 3, max_photo_gap_hours: float = 4.0):
        self.min_photo_count = min_photo_count
        self.max_photo_gap_hours = max_photo_gap_hours

    def validate(self, record: PouringRecord) -> PouringRecord:
        record.issues = []
        self._check_required_fields(record)
        self._check_supervisor_sign(record)
        self._check_log_file(record)
        self._check_photos(record)
        return record

    def validate_all(self, records: List[PouringRecord]) -> List[PouringRecord]:
        for r in records:
            self.validate(r)
        return records

    def _check_required_fields(self, record: PouringRecord):
        for attr, issue_type, severity, field_name in self.REQUIRED_FIELDS:
            value = getattr(record, attr)
            if value is None or str(value).strip() == "":
                record.issues.append(Issue(
                    issue_type=issue_type,
                    severity=severity,
                    description=f"缺少【{field_name}】未填写",
                    field_name=field_name,
                ))

    def _check_supervisor_sign(self, record: PouringRecord):
        if not record.has_supervisor_sign:
            desc = "缺少监理签名"
            if record.supervisor:
                desc = f"监理员【{record.supervisor}】未签名"
            record.issues.append(Issue(
                issue_type=IssueType.MISSING_SUPERVISOR_SIGN,
                severity=Severity.CRITICAL,
                description=desc,
                field_name="监理签名",
            ))

    def _check_log_file(self, record: PouringRecord):
        if not record.log_file_path:
            record.issues.append(Issue(
                issue_type=IssueType.MISSING_LOG,
                severity=Severity.HIGH,
                description="未找到旁站日志文件",
                field_name="旁站日志",
            ))

    def _check_photos(self, record: PouringRecord):
        if len(record.photos) < self.min_photo_count:
            record.issues.append(Issue(
                issue_type=IssueType.MISSING_PHOTO,
                severity=Severity.MEDIUM,
                description=f"旁站照片数量不足（应有≥{self.min_photo_count}张，实际{len(record.photos)}张）",
                field_name="照片数量",
                expected=f">={self.min_photo_count}",
                actual=str(len(record.photos)),
            ))

        if len(record.photos) >= 2 and record.pouring_date:
            self._check_photo_time_coherence(record)

    def _check_photo_time_coherence(self, record: PouringRecord):
        valid_photos = [p for p in record.photos if p.shoot_time and p.is_valid]
        if not valid_photos:
            return

        valid_photos.sort(key=lambda x: x.shoot_time)

        pour_date = record.pouring_date.date()
        first_photo = valid_photos[0].shoot_time
        last_photo = valid_photos[-1].shoot_time

        if first_photo and first_photo.date() > pour_date + timedelta(days=1):
            return
        if first_photo and first_photo.date() < pour_date - timedelta(days=1):
            record.issues.append(Issue(
                issue_type=IssueType.PHOTO_TIME_MISMATCH,
                severity=Severity.MEDIUM,
                description=f"最早照片日期{first_photo.strftime('%Y-%m-%d')}与浇筑日期{pour_date.strftime('%Y-%m-%d')}不符",
                field_name="照片时间",
                expected=f"应在浇筑日期前后1天内",
                actual=first_photo.strftime('%Y-%m-%d') if first_photo else "",
            ))

        gap_issues = []
        for i in range(1, len(valid_photos)):
            prev = valid_photos[i - 1].shoot_time
            curr = valid_photos[i].shoot_time
            if prev and curr:
                gap = (curr - prev).total_seconds() / 3600.0
                if gap > self.max_photo_gap_hours:
                    gap_issues.append((i, gap, prev, curr))

        if gap_issues:
            idx, gap, prev_t, curr_t = gap_issues[0]
            record.issues.append(Issue(
                issue_type=IssueType.PHOTO_TIME_MISMATCH,
                severity=Severity.LOW,
                description=f"照片时间间隔过大（{gap:.1f}小时），旁站记录可能不完整",
                field_name="照片时间间隔",
                expected=f"≤{self.max_photo_gap_hours}小时",
                actual=f"{gap:.1f}小时",
            ))


def get_records_with_issues(records: List[PouringRecord]) -> List[PouringRecord]:
    return [r for r in records if r.has_issues]


def get_records_by_severity(records: List[PouringRecord], severity: Severity) -> List[PouringRecord]:
    result = []
    for r in records:
        if any(i.severity == severity for i in r.issues):
            result.append(r)
    return result


def get_statistics(records: List[PouringRecord]) -> dict:
    total = len(records)
    total_count = len(records)
    with_issues = [r for r in records if r.has_issues]
    no_issues = [r for r in records if not r.has_issues]

    issue_counts = {}
    severity_counts = {s: 0 for s in Severity}
    for r in records:
        for issue in r.issues:
            key = issue.issue_type
            issue_counts[key] = issue_counts.get(key, 0) + 1
            severity_counts[issue.severity] += 1

    buildings = set(r.building for r in records if r.building)
    supervisors = set(r.supervisor for r in records if r.supervisor)

    return {
        "总记录数": total_count,
        "有问题记录": len(with_issues),
        "合格记录": len(no_issues),
        "合格率": f"{(len(no_issues) / total_count * 100):.1f}%" if total_count > 0 else "0%",
        "总问题数": sum(issue_counts.values()),
        "问题类型分布": {k.value: v for k, v in issue_counts.items()},
        "严重程度分布": {k.value: v for k, v in severity_counts.items()},
        "涉及楼栋数": len(buildings),
        "涉及监理员数": len(supervisors),
        "楼栋列表": sorted(list(buildings)),
        "监理员列表": sorted(list(supervisors)),
    }
