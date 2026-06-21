from typing import List, Optional, Set
from datetime import datetime

from .models import PouringRecord, Severity, IssueType


class RecordFilter:
    @staticmethod
    def by_building(records: List[PouringRecord], building: str) -> List[PouringRecord]:
        if not building:
            return records
        target = building.strip().lower()
        result = []
        for r in records:
            b = (r.building or "").strip().lower()
            if target in b or b in target:
                result.append(r)
        return result

    @staticmethod
    def by_supervisor(records: List[PouringRecord], supervisor: str) -> List[PouringRecord]:
        if not supervisor:
            return records
        target = supervisor.strip()
        result = []
        for r in records:
            s = r.supervisor or ""
            if target in s or s in target:
                result.append(r)
        return result

    @staticmethod
    def by_issue_type(records: List[PouringRecord], issue_types: List[IssueType]) -> List[PouringRecord]:
        if not issue_types:
            return records
        type_set = set(issue_types)
        result = []
        for r in records:
            if any(i.issue_type in type_set for i in r.issues):
                result.append(r)
        return result

    @staticmethod
    def by_severity(records: List[PouringRecord], min_severity: Severity) -> List[PouringRecord]:
        result = []
        for r in records:
            hs = r.highest_severity
            if hs and hs.order <= min_severity.order:
                result.append(r)
        return result

    @staticmethod
    def by_date_range(
        records: List[PouringRecord],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> List[PouringRecord]:
        result = []
        for r in records:
            if not r.pouring_date:
                continue
            ok = True
            if start_date and r.pouring_date < start_date:
                ok = False
            if end_date and r.pouring_date > end_date:
                ok = False
            if ok:
                result.append(r)
        return result

    @staticmethod
    def only_with_issues(records: List[PouringRecord]) -> List[PouringRecord]:
        return [r for r in records if r.has_issues]

    @staticmethod
    def by_keyword(records: List[PouringRecord], keyword: str) -> List[PouringRecord]:
        if not keyword:
            return records
        kw = keyword.strip().lower()
        result = []
        for r in records:
            haystack_parts = [
                r.building or "",
                r.position or "",
                r.strength_grade or "",
                r.supervisor or "",
                r.record_id or "",
            ]
            haystack = " ".join(haystack_parts).lower()
            issue_text = " ".join([i.description for i in r.issues]).lower()
            if kw in haystack or kw in issue_text:
                result.append(r)
        return result

    @staticmethod
    def apply_filters(
        records: List[PouringRecord],
        building: Optional[str] = None,
        supervisor: Optional[str] = None,
        issue_types: Optional[List[IssueType]] = None,
        min_severity: Optional[Severity] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        keyword: Optional[str] = None,
        issues_only: bool = True,
    ) -> List[PouringRecord]:
        filtered = records
        if issues_only:
            filtered = RecordFilter.only_with_issues(filtered)
        if building:
            filtered = RecordFilter.by_building(filtered, building)
        if supervisor:
            filtered = RecordFilter.by_supervisor(filtered, supervisor)
        if issue_types:
            filtered = RecordFilter.by_issue_type(filtered, issue_types)
        if min_severity:
            filtered = RecordFilter.by_severity(filtered, min_severity)
        if start_date or end_date:
            filtered = RecordFilter.by_date_range(filtered, start_date, end_date)
        if keyword:
            filtered = RecordFilter.by_keyword(filtered, keyword)
        return filtered

    @staticmethod
    def unique_buildings(records: List[PouringRecord]) -> List[str]:
        buildings = set()
        for r in records:
            if r.building:
                buildings.add(r.building)
        return sorted(list(buildings))

    @staticmethod
    def unique_supervisors(records: List[PouringRecord]) -> List[str]:
        supervisors = set()
        for r in records:
            if r.supervisor:
                supervisors.add(r.supervisor)
        return sorted(list(supervisors))
