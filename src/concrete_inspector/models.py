from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class Severity(Enum):
    CRITICAL = "严重"
    HIGH = "重要"
    MEDIUM = "一般"
    LOW = "轻微"

    @property
    def order(self):
        order_map = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }
        return order_map[self]


class IssueType(Enum):
    MISSING_POSITION = "缺少部位"
    MISSING_STRENGTH = "缺少强度等级"
    MISSING_SLUMP = "缺少坍落度"
    MISSING_SAMPLE_COUNT = "缺少试块组数"
    MISSING_SUPERVISOR_SIGN = "缺少监理签名"
    MISSING_PHOTO = "缺少旁站照片"
    PHOTO_TIME_MISMATCH = "照片时间不连贯"
    MISSING_LOG = "缺少旁站日志"
    INVALID_DATE = "日期格式错误"


@dataclass
class Issue:
    issue_type: IssueType
    severity: Severity
    description: str
    field_name: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None


@dataclass
class PhotoRecord:
    file_path: str
    file_name: str
    shoot_time: Optional[datetime] = None
    is_valid: bool = True


@dataclass
class PouringRecord:
    record_id: str
    log_file_path: Optional[str] = None
    log_file_name: Optional[str] = None
    project_name: str = ""
    building: str = ""
    pouring_date: Optional[datetime] = None
    position: Optional[str] = None
    strength_grade: Optional[str] = None
    slump: Optional[str] = None
    sample_count: Optional[str] = None
    supervisor: Optional[str] = None
    has_supervisor_sign: bool = False
    photos: List[PhotoRecord] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def critical_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def highest_severity(self) -> Optional[Severity]:
        if not self.issues:
            return None
        return min(self.issues, key=lambda x: x.severity.order).severity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "记录编号": self.record_id,
            "项目名称": self.project_name,
            "楼栋号": self.building,
            "浇筑日期": self.pouring_date.strftime("%Y-%m-%d") if self.pouring_date else "",
            "浇筑部位": self.position or "",
            "强度等级": self.strength_grade or "",
            "坍落度": self.slump or "",
            "试块组数": self.sample_count or "",
            "监理员": self.supervisor or "",
            "监理签名": "有" if self.has_supervisor_sign else "无",
            "照片数量": len(self.photos),
            "问题数量": len(self.issues),
            "最高严重程度": self.highest_severity.value if self.highest_severity else "",
            "问题描述": "; ".join([i.description for i in self.issues]),
        }
