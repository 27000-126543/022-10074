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
    PHOTO_TIME_MISMATCH = "照片时间异常"
    MISSING_LOG = "缺少旁站日志"
    INVALID_DATE = "日期格式错误"
    CONSISTENCY_BUILDING = "楼栋号不一致"
    CONSISTENCY_POSITION = "部位不一致"
    CONSISTENCY_STRENGTH = "强度等级不一致"
    CONSISTENCY_SUPERVISOR = "监理员不一致"
    CONSISTENCY_DATE = "浇筑日期不一致"


@dataclass
class Issue:
    issue_type: IssueType
    severity: Severity
    description: str
    field_name: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    suggestion: Optional[str] = None
    responsible: Optional[str] = None
    source_values: Optional[Dict[str, str]] = None


@dataclass
class PhotoRecord:
    file_path: str
    file_name: str
    shoot_time: Optional[datetime] = None
    is_valid: bool = True


@dataclass
class FieldSource:
    folder: Optional[str] = None
    log: Optional[str] = None
    manifest: Optional[str] = None

    def all_values(self) -> List[str]:
        return [v.strip() for v in [self.folder, self.log, self.manifest]
                if v is not None and str(v).strip() != "" and str(v).lower() != "nan"]

    def has_conflict(self) -> bool:
        vals = self.all_values()
        if len(vals) < 2:
            return False
        normalized = []
        for v in vals:
            n = str(v).replace(" ", "").replace("号楼", "").replace("#", "")
            normalized.append(n)
        return len(set(normalized)) > 1

    def conflict_summary(self) -> str:
        parts = []
        if self.folder is not None:
            parts.append(f"文件夹名：{self.folder}")
        if self.log is not None:
            parts.append(f"日志：{self.log}")
        if self.manifest is not None:
            parts.append(f"清单：{self.manifest}")
        return " | ".join(parts)


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
    source_building: FieldSource = field(default_factory=FieldSource)
    source_position: FieldSource = field(default_factory=FieldSource)
    source_strength: FieldSource = field(default_factory=FieldSource)
    source_supervisor: FieldSource = field(default_factory=FieldSource)
    source_date: FieldSource = field(default_factory=FieldSource)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def critical_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def consistency_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.issue_type.name.startswith("CONSISTENCY_")]

    @property
    def highest_severity(self) -> Optional[Severity]:
        if not self.issues:
            return None
        return min(self.issues, key=lambda x: x.severity.order).severity

    def get_field_source(self, field_name: str) -> FieldSource:
        mapping = {
            "building": self.source_building,
            "position": self.source_position,
            "strength_grade": self.source_strength,
            "supervisor": self.source_supervisor,
            "pouring_date": self.source_date,
        }
        return mapping.get(field_name, FieldSource())

    def to_dict(self) -> Dict[str, Any]:
        consistency_flags = []
        if self.source_building.has_conflict():
            consistency_flags.append("楼栋")
        if self.source_position.has_conflict():
            consistency_flags.append("部位")
        if self.source_strength.has_conflict():
            consistency_flags.append("强度")
        if self.source_supervisor.has_conflict():
            consistency_flags.append("监理员")
        if self.source_date.has_conflict():
            consistency_flags.append("日期")

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
            "资料一致性": "⚠️冲突：" + "、".join(consistency_flags) if consistency_flags else "✅一致",
            "问题数量": len(self.issues),
            "最高严重程度": self.highest_severity.value if self.highest_severity else "",
            "问题描述": "; ".join([i.description for i in self.issues]),
        }
