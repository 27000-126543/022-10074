from datetime import datetime, timedelta
from typing import List, Optional

from .models import (
    PouringRecord,
    Issue,
    IssueType,
    Severity,
    PhotoRecord,
)
from .rules import InspectionRules, ISSUE_TYPE_TO_KEY


FIELD_LABEL = {
    "building": "楼栋号",
    "position": "浇筑部位",
    "strength_grade": "强度等级",
    "slump": "坍落度",
    "sample_count": "试块组数",
    "supervisor": "监理员",
    "pouring_date": "浇筑日期",
}

FIELD_CONSISTENCY_ISSUE = {
    "building": IssueType.CONSISTENCY_BUILDING,
    "position": IssueType.CONSISTENCY_POSITION,
    "strength_grade": IssueType.CONSISTENCY_STRENGTH,
    "supervisor": IssueType.CONSISTENCY_SUPERVISOR,
    "pouring_date": IssueType.CONSISTENCY_DATE,
}


class RecordValidator:
    def __init__(self, rules: Optional[InspectionRules] = None):
        self.rules = rules or InspectionRules.default()

    def _get_issue_key(self, itype: IssueType) -> str:
        return ISSUE_TYPE_TO_KEY.get(itype, itype.name.lower())

    def _wrap_issue(self, issue: Issue) -> Issue:
        key = self._get_issue_key(issue.issue_type)
        issue.severity = self.rules.get_effective_severity(key, issue.severity)
        if issue.suggestion is None:
            issue.suggestion = self.rules.get_suggestion(key)
        if issue.responsible is None:
            issue.responsible = self.rules.get_responsible(key)
        return issue

    def validate(self, record: PouringRecord) -> PouringRecord:
        record.issues = []
        self._check_required_fields(record)
        if self.rules.require_supervisor_sign:
            self._check_supervisor_sign(record)
        self._check_log_file(record)
        self._check_photos(record)
        if self.rules.consistency_check:
            self._check_consistency(record)

        record.issues = [self._wrap_issue(i) for i in record.issues]
        return record

    def validate_all(self, records: List[PouringRecord]) -> List[PouringRecord]:
        for r in records:
            self.validate(r)
        return records

    def _check_required_fields(self, record: PouringRecord):
        for attr_name, cfg in self.rules.required_fields.items():
            if not cfg.get("required", True):
                continue
            value = getattr(record, attr_name, None)
            if value is None or str(value).strip() == "" or str(value).lower() == "nan":
                label = cfg.get("label", FIELD_LABEL.get(attr_name, attr_name))
                severity = cfg.get("severity", Severity.HIGH)
                record.issues.append(Issue(
                    issue_type=self._get_missing_issue_type(attr_name),
                    severity=severity,
                    description=f"缺少【{label}】未填写",
                    field_name=label,
                ))

    def _get_missing_issue_type(self, attr_name: str) -> IssueType:
        mapping = {
            "position": IssueType.MISSING_POSITION,
            "strength_grade": IssueType.MISSING_STRENGTH,
            "slump": IssueType.MISSING_SLUMP,
            "sample_count": IssueType.MISSING_SAMPLE_COUNT,
        }
        return mapping.get(attr_name, IssueType.MISSING_POSITION)

    def _check_supervisor_sign(self, record: PouringRecord):
        if not record.has_supervisor_sign:
            desc = "缺少监理签名"
            if record.supervisor:
                desc = f"监理员【{record.supervisor}】未签名"
            record.issues.append(Issue(
                issue_type=IssueType.MISSING_SUPERVISOR_SIGN,
                severity=self.rules.supervisor_sign_severity,
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
        if len(record.photos) < self.rules.min_photo_count:
            record.issues.append(Issue(
                issue_type=IssueType.MISSING_PHOTO,
                severity=Severity.MEDIUM,
                description=f"旁站照片数量不足（应有≥{self.rules.min_photo_count}张，实际{len(record.photos)}张）",
                field_name="照片数量",
                expected=f">={self.rules.min_photo_count}",
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

        early_threshold = timedelta(days=self.rules.photo_early_days)
        late_threshold = timedelta(days=self.rules.photo_late_days)

        if first_photo:
            fp_date = first_photo.date()
            days_early = (pour_date - fp_date).days
            if days_early > self.rules.photo_early_days:
                record.issues.append(Issue(
                    issue_type=IssueType.PHOTO_TIME_MISMATCH,
                    severity=Severity.HIGH,
                    description=(
                        f"照片整体早于浇筑日期{days_early}天 "
                        f"（最早{first_photo.strftime('%Y-%m-%d')}，"
                        f"浇筑{pour_date.strftime('%Y-%m-%d')}），超出允许提前{self.rules.photo_early_days}天范围"
                    ),
                    field_name="照片时间",
                    expected=f"不早于浇筑前{self.rules.photo_early_days}天",
                    actual=f"早了{days_early}天",
                ))

        if last_photo:
            lp_date = last_photo.date()
            days_late = (lp_date - pour_date).days
            if days_late > self.rules.photo_late_days:
                record.issues.append(Issue(
                    issue_type=IssueType.PHOTO_TIME_MISMATCH,
                    severity=Severity.HIGH,
                    description=(
                        f"照片整体晚于浇筑日期{days_late}天 "
                        f"（最晚{last_photo.strftime('%Y-%m-%d')}，"
                        f"浇筑{pour_date.strftime('%Y-%m-%d')}），超出允许滞后{self.rules.photo_late_days}天范围"
                    ),
                    field_name="照片时间",
                    expected=f"不晚于浇筑后{self.rules.photo_late_days}天",
                    actual=f"晚了{days_late}天",
                ))

        gap_issues = []
        for i in range(1, len(valid_photos)):
            prev = valid_photos[i - 1].shoot_time
            curr = valid_photos[i].shoot_time
            if prev and curr:
                gap = (curr - prev).total_seconds() / 3600.0
                if gap > self.rules.max_photo_gap_hours:
                    gap_issues.append((i, gap, prev, curr))

        if gap_issues:
            idx, gap, prev_t, curr_t = gap_issues[0]
            record.issues.append(Issue(
                issue_type=IssueType.PHOTO_TIME_MISMATCH,
                severity=Severity.LOW,
                description=f"照片时间间隔过大（{gap:.1f}小时），旁站记录可能不完整",
                field_name="照片时间间隔",
                expected=f"≤{self.rules.max_photo_gap_hours}小时",
                actual=f"{gap:.1f}小时",
            ))

    def _check_consistency(self, record: PouringRecord):
        for field_name in self.rules.consistency_fields:
            source = record.get_field_source(field_name)
            if not source.has_conflict():
                continue

            issue_type = FIELD_CONSISTENCY_ISSUE.get(field_name)
            if issue_type is None:
                continue
            label = FIELD_LABEL.get(field_name, field_name)

            vals = source.all_values()
            norm = set()
            for v in vals:
                n = str(v).replace(" ", "")
                if field_name == "building":
                    n = n.replace("号楼", "").replace("#", "")
                elif field_name == "strength_grade":
                    n = n.upper()
                norm.add(n)

            if len(norm) <= 1:
                continue

            parts = source.conflict_summary()
            record.issues.append(Issue(
                issue_type=issue_type,
                severity=self.rules.consistency_severity,
                description=f"【{label}】资料不一致：{parts}",
                field_name=label,
                source_values={
                    "folder": source.folder,
                    "log": source.log,
                    "manifest": source.manifest,
                },
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
    total_count = len(records)
    with_issues = [r for r in records if r.has_issues]
    no_issues = [r for r in records if not r.has_issues]

    issue_counts = {}
    severity_counts = {s: 0 for s in Severity}
    consistency_count = 0
    for r in records:
        for issue in r.issues:
            key = issue.issue_type
            issue_counts[key] = issue_counts.get(key, 0) + 1
            severity_counts[issue.severity] += 1
            if issue.issue_type.name.startswith("CONSISTENCY_"):
                consistency_count += 1

    buildings = set(r.building for r in records if r.building)
    supervisors = set(r.supervisor for r in records if r.supervisor)

    return {
        "总记录数": total_count,
        "有问题记录": len(with_issues),
        "合格记录": len(no_issues),
        "合格率": f"{(len(no_issues) / total_count * 100):.1f}%" if total_count > 0 else "0%",
        "总问题数": sum(issue_counts.values()),
        "一致性冲突数": consistency_count,
        "问题类型分布": {k.value: v for k, v in issue_counts.items()},
        "严重程度分布": {k.value: v for k, v in severity_counts.items()},
        "涉及楼栋数": len(buildings),
        "涉及监理员数": len(supervisors),
        "楼栋列表": sorted(list(buildings)),
        "监理员列表": sorted(list(supervisors)),
    }
