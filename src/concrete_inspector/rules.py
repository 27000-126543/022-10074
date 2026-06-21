import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import Severity, IssueType


DEFAULT_RULES = {
    "min_photo_count": 3,
    "max_photo_gap_hours": 4.0,
    "photo_early_days": 1,
    "photo_late_days": 1,
    "required_fields": {
        "position": {"severity": "critical", "label": "浇筑部位", "required": True},
        "strength_grade": {"severity": "critical", "label": "强度等级", "required": True},
        "slump": {"severity": "high", "label": "坍落度", "required": True},
        "sample_count": {"severity": "high", "label": "试块组数", "required": True},
    },
    "require_supervisor_sign": True,
    "supervisor_sign_severity": "critical",
    "issue_severity_override": {},
    "consistency_check": True,
    "consistency_fields": ["building", "position", "strength_grade", "supervisor"],
    "consistency_severity": "high",
    "suggestions": {
        "missing_position": "请联系现场资料员补填浇筑部位（具体到层号+梁板/柱墙/承台），并在日志中同步更新",
        "missing_strength": "请根据配合比通知单补填强度等级，如有抗渗/抗冻要求需一并注明",
        "missing_slump": "请根据开盘鉴定或现场实测数据补填坍落度值（如 160±20mm）",
        "missing_sample_count": "请按规范要求补填试块组数（≥100m³不少于1组，不足100m³也需1组）",
        "missing_supervisor_sign": "请通知该旁站监理员在24小时内完成补签，原件扫描存档",
        "missing_photo": "请要求施工单位补充旁站过程照片（开盘、浇筑中、收面各至少1张），照片需显示部位和时间水印",
        "photo_time_mismatch": "请核对照片拍摄时间与实际浇筑时段，必要时补充说明或更换原始照片",
        "missing_log": "请补做旁站监理日志，需包含人、机、料、法、环五要素并签名",
        "consistency_conflict": "请核对文件夹名、旁站日志、浇筑清单中的字段，保持三处信息一致后重新归档",
    },
    "responsible_roles": {
        "missing_position": "施工资料员",
        "missing_strength": "施工技术员",
        "missing_slump": "试验员",
        "missing_sample_count": "试验员",
        "missing_supervisor_sign": "旁站监理员",
        "missing_photo": "施工资料员",
        "photo_time_mismatch": "施工资料员",
        "missing_log": "旁站监理员",
        "consistency_conflict": "项目质量总监",
    },
}


SEVERITY_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
}


@dataclass
class InspectionRules:
    min_photo_count: int = 3
    max_photo_gap_hours: float = 4.0
    photo_early_days: int = 1
    photo_late_days: int = 1
    required_fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    require_supervisor_sign: bool = True
    supervisor_sign_severity: Severity = Severity.CRITICAL
    issue_severity_override: Dict[str, str] = field(default_factory=dict)
    consistency_check: bool = True
    consistency_fields: List[str] = field(default_factory=list)
    consistency_severity: Severity = Severity.HIGH
    suggestions: Dict[str, str] = field(default_factory=dict)
    responsible_roles: Dict[str, str] = field(default_factory=dict)
    source_file: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict, source: Optional[str] = None) -> "InspectionRules":
        merged = {k: v for k, v in DEFAULT_RULES.items()}
        if data:
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                elif isinstance(v, list) and isinstance(merged.get(k), list):
                    merged[k] = list(v)
                else:
                    merged[k] = v

        req_fields = {}
        for fname, fcfg in merged["required_fields"].items():
            req_fields[fname] = {
                "severity": SEVERITY_MAP.get(fcfg.get("severity", "high"), Severity.HIGH),
                "label": fcfg.get("label", fname),
                "required": fcfg.get("required", True),
            }

        sev_override = {}
        for k, v in (merged.get("issue_severity_override") or {}).items():
            if isinstance(v, str) and v.lower() in SEVERITY_MAP:
                sev_override[k] = v.lower()

        return cls(
            min_photo_count=int(merged["min_photo_count"]),
            max_photo_gap_hours=float(merged["max_photo_gap_hours"]),
            photo_early_days=int(merged["photo_early_days"]),
            photo_late_days=int(merged["photo_late_days"]),
            required_fields=req_fields,
            require_supervisor_sign=bool(merged["require_supervisor_sign"]),
            supervisor_sign_severity=SEVERITY_MAP.get(
                str(merged["supervisor_sign_severity"]).lower(), Severity.CRITICAL
            ),
            issue_severity_override=sev_override,
            consistency_check=bool(merged["consistency_check"]),
            consistency_fields=list(merged["consistency_fields"]),
            consistency_severity=SEVERITY_MAP.get(
                str(merged["consistency_severity"]).lower(), Severity.HIGH
            ),
            suggestions=dict(merged["suggestions"] or {}),
            responsible_roles=dict(merged["responsible_roles"] or {}),
            source_file=source,
        )

    @classmethod
    def default(cls) -> "InspectionRules":
        return cls.from_dict(DEFAULT_RULES)

    def get_effective_severity(self, issue_key: str, default: Severity) -> Severity:
        override = self.issue_severity_override.get(issue_key)
        if override and override in SEVERITY_MAP:
            return SEVERITY_MAP[override]
        return default

    def get_suggestion(self, issue_key: str) -> str:
        key = issue_key.lower()
        if key in self.suggestions:
            return self.suggestions[key]
        if key.startswith("consistency_"):
            return self.suggestions.get("consistency_conflict", "请核对资料后补填正确信息")
        return "请补全相关资料"

    def get_responsible(self, issue_key: str) -> str:
        key = issue_key.lower()
        if key in self.responsible_roles:
            return self.responsible_roles[key]
        if key.startswith("consistency_"):
            return self.responsible_roles.get("consistency_conflict", "项目质量负责人")
        return "相关责任人"

    def to_dict(self) -> dict:
        data = {
            "min_photo_count": self.min_photo_count,
            "max_photo_gap_hours": self.max_photo_gap_hours,
            "photo_early_days": self.photo_early_days,
            "photo_late_days": self.photo_late_days,
            "required_fields": {},
            "require_supervisor_sign": self.require_supervisor_sign,
            "supervisor_sign_severity": self.supervisor_sign_severity.name.lower(),
            "issue_severity_override": dict(self.issue_severity_override),
            "consistency_check": self.consistency_check,
            "consistency_fields": list(self.consistency_fields),
            "consistency_severity": self.consistency_severity.name.lower(),
            "suggestions": dict(self.suggestions),
            "responsible_roles": dict(self.responsible_roles),
        }
        for fname, fcfg in self.required_fields.items():
            data["required_fields"][fname] = {
                "severity": fcfg["severity"].name.lower(),
                "label": fcfg["label"],
                "required": fcfg["required"],
            }
        return data

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


ISSUE_TYPE_TO_KEY = {
    IssueType.MISSING_POSITION: "missing_position",
    IssueType.MISSING_STRENGTH: "missing_strength",
    IssueType.MISSING_SLUMP: "missing_slump",
    IssueType.MISSING_SAMPLE_COUNT: "missing_sample_count",
    IssueType.MISSING_SUPERVISOR_SIGN: "missing_supervisor_sign",
    IssueType.MISSING_PHOTO: "missing_photo",
    IssueType.PHOTO_TIME_MISMATCH: "photo_time_mismatch",
    IssueType.MISSING_LOG: "missing_log",
    IssueType.INVALID_DATE: "invalid_date",
}


def load_rules(project_dir: Optional[str] = None,
               config_path: Optional[str] = None) -> InspectionRules:
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    if project_dir:
        p = Path(project_dir)
        candidates.append(p / "inspection_rules.json")
        candidates.append(p / ".inspection_rules.json")
        candidates.append(p / "rules.json")
        candidates.append(p / "检查规则.json")
    candidates.append(Path.cwd() / "inspection_rules.json")
    candidates.append(Path.home() / ".concrete_inspector" / "rules.json")

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return InspectionRules.from_dict(data, source=str(candidate))
            except (json.JSONDecodeError, OSError) as e:
                print(f"⚠️  读取规则文件 {candidate} 失败：{e}，使用默认规则")

    return InspectionRules.default()


def generate_sample_rules(output_path: str):
    rules = InspectionRules.default()
    data = rules.to_dict()
    data["_说明_"] = {
        "min_photo_count": "每次浇筑最少照片张数",
        "max_photo_gap_hours": "相邻照片最大允许间隔（小时），超过则提示时间不连贯",
        "photo_early_days": "照片最早可早于浇筑日期多少天（超出算时间异常）",
        "photo_late_days": "照片最晚可晚于浇筑日期多少天（超出算时间异常）",
        "required_fields": "必填字段配置，severity可选critical/high/medium/low",
        "require_supervisor_sign": "是否强制要求监理签名",
        "issue_severity_override": "覆盖特定问题类型的严重程度，如 {\"missing_photo\": \"high\"}",
        "consistency_check": "是否启用文件夹名/日志/清单三方一致性核对",
        "consistency_fields": "参与一致性核对的字段",
        "consistency_severity": "一致性冲突的默认严重程度",
        "suggestions": "每种问题类型对应的整改建议（用于导出CSV）",
        "responsible_roles": "每种问题类型对应的责任人岗位（用于导出CSV）",
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 示例规则文件已生成：{out.resolve()}")
