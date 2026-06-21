import os
import re
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import logging

from PIL import Image
from PIL.ExifTags import TAGS

from .models import PouringRecord, PhotoRecord, FieldSource

logger = logging.getLogger(__name__)


DATE_PATTERNS = [
    re.compile(r"(\d{4})[-_年\.](\d{1,2})[-_月\.](\d{1,2})"),
    re.compile(r"(\d{4})(\d{2})(\d{2})"),
    re.compile(r"(\d{2})[-_年\.](\d{1,2})[-_月\.](\d{1,2})"),
]

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}
LOG_EXTENSIONS = {".xlsx", ".xls", ".csv", ".txt", ".docx", ".doc"}


def parse_date_from_string(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    try:
        import math
        if isinstance(s, float) and math.isnan(s):
            return None
    except Exception:
        pass
    s = str(s).strip()
    if s == "" or s.lower() == "nan":
        return None
    for pattern in DATE_PATTERNS:
        m = pattern.search(s)
        if m:
            try:
                groups = m.groups()
                if len(groups[0]) == 4:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                else:
                    year = 2000 + int(groups[0])
                    month, day = int(groups[1]), int(groups[2])
                return datetime(year, month, day)
            except (ValueError, IndexError):
                continue
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return True
    except Exception:
        pass
    s = str(v).strip()
    return s == "" or s.lower() == "nan"


def extract_date_from_filename(filename: str) -> Optional[datetime]:
    return parse_date_from_string(filename)


def extract_building_from_name(name: str) -> str:
    patterns = [
        re.compile(r"(\d+)\s*号楼?"),
        re.compile(r"[A-Za-z](\d+)\s*栋"),
        re.compile(r"(\d+)\s*#"),
        re.compile(r"(\d+)\s*区"),
    ]
    for p in patterns:
        m = p.search(name)
        if m:
            return f"{m.group(1)}号楼"
    return ""


def extract_position_from_name(name: str) -> Optional[str]:
    patterns = [
        r"(\d+层[一二三四五六七八九十百千万]*(?:梁板|梁板柱|柱墙|墙板|基础承台|承台|基础|梁|板|柱|墙)?)",
        r"([一二三四五六七八九十百千万]+层(?:梁板|梁板柱|柱墙|墙板|基础承台|承台|基础|梁|板|柱|墙)?)",
        r"(\d+F\s*(?:梁板|梁板柱|柱墙|墙板|基础承台|承台|基础|梁|板|柱|墙)?)",
        r"(地下室负?\d*层(?:梁板|梁板柱|柱墙|墙板|基础承台|承台|基础|梁|板|柱|墙)?)",
        r"(地下室负?\d*(?:梁板|梁板柱|柱墙|墙板|基础承台|承台|基础|梁|板|柱|墙)?)",
    ]
    for p in patterns:
        m = re.search(p, name)
        if m:
            val = m.group(1)
            if val and len(val) > 1:
                return val
    return None


def extract_strength_from_name(name: str) -> Optional[str]:
    m = re.search(r"(C\d+(?:[A-Za-z]+\d+)*[A-Za-z]*)", name)
    if m:
        return m.group(1)
    return None


def extract_slump_from_name(name: str) -> Optional[str]:
    m = re.search(r"坍落度\s*[:：]?\s*(\d+[±~]?\d*mm?)", name)
    if m:
        return m.group(1)
    m = re.search(r"(\d+[±~]?\d*)\s*mm", name)
    if m:
        return f"{m.group(1)}mm"
    return None


def extract_sample_count_from_name(name: str) -> Optional[str]:
    m = re.search(r"试块\s*[:：]?\s*(\d+)\s*组", name)
    if m:
        return m.group(1)
    m = re.search(r"(\d+)\s*组\s*试块", name)
    if m:
        return m.group(1)
    return None


def extract_supervisor_from_name(name: str) -> Optional[str]:
    patterns = [
        re.compile(r"监理员?\s*[:：]\s*([\u4e00-\u9fa5]{2,4}(?![签字]))"),
        re.compile(r"旁站(?!人员|签名|签字)\s*[:：]?\s*([\u4e00-\u9fa5]{2,4}(?![签字]))"),
    ]
    for p in patterns:
        m = p.search(name)
        if m:
            name_val = m.group(1)
            if name_val in ("签名", "签字", "旁站", "监理"):
                continue
            return name_val
    return None


def get_photo_datetime(file_path: str) -> Optional[datetime]:
    try:
        img = Image.open(file_path)
        exif_data = img._getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in ("DateTimeOriginal", "DateTime"):
                    try:
                        return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        continue
    except Exception as e:
        logger.debug(f"读取照片EXIF失败 {file_path}: {e}")
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)
    except Exception:
        return None


def extract_fields_from_text(text: str) -> Dict[str, Any]:
    """从纯文本（日志内容）中提取各字段值"""
    result = {}
    if not text:
        return result
    try:
        m = re.search(r"楼栋号?\s*[:：]\s*([^\n\r]+)", text)
        if m:
            val = m.group(1).strip()
            if not _is_empty(val):
                bld = extract_building_from_name(val)
                result["building"] = bld or val

        m = re.search(r"浇筑部位\s*[:：]\s*([^\n\r]+)|部位\s*[:：]\s*([^\n\r]+)", text)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            if not _is_empty(val):
                pos = extract_position_from_name(val)
                result["position"] = pos or val

        m = re.search(r"强度等级?\s*[:：]\s*([^\n\r]+)", text)
        if m:
            val = m.group(1).strip()
            if not _is_empty(val):
                st = extract_strength_from_name(val)
                result["strength_grade"] = st or val

        m = re.search(r"坍落度\s*[:：]\s*([^\n\r]+)", text)
        if m:
            val = m.group(1).strip()
            if not _is_empty(val):
                sl = extract_slump_from_name(val)
                result["slump"] = sl or val

        m = re.search(r"试块组数\s*[:：]\s*([^\n\r]+)|试块\s*[:：]\s*(\d+)\s*组", text)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            if not _is_empty(val):
                sc = extract_sample_count_from_name(val)
                result["sample_count"] = sc or val

        m = re.search(r"旁站监理员?\s*[:：]\s*([^\n\r]+)|监理员?\s*[:：]\s*([^\n\r]+)", text)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            if not _is_empty(val):
                sp = extract_supervisor_from_name(val)
                result["supervisor"] = sp or val

        m = re.search(r"浇筑日期\s*[:：]\s*([^\n\r]+)|日期\s*[:：]\s*([^\n\r]+)", text)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            if not _is_empty(val):
                dt = parse_date_from_string(val)
                if dt:
                    result["pouring_date"] = dt

        has_sign = False
        signed_patterns = [
            r"监理员?签名[:：]?\s*[\u4e00-\u9fa5]{2,4}(?!\s*[_—]+)",
            r"签名[:：]?\s*[\u4e00-\u9fa5]{2,4}(?!\s*[_—]+)",
            r"签字[:：]?\s*[\u4e00-\u9fa5]{2,4}(?!\s*[_—]+)",
            r"[\u4e00-\u9fa5]{2,4}\s*[（(]\s*已签\s*[)）]",
        ]
        for pat in signed_patterns:
            if re.search(pat, text):
                has_sign = True
                break
        result["has_supervisor_sign"] = has_sign
    except Exception as e:
        logger.debug(f"从文本提取字段失败：{e}")
    return result


class DirectoryScanner:
    def __init__(self, project_dir: str, date_range: Optional[Tuple[datetime, datetime]] = None):
        self.project_dir = Path(project_dir)
        self.date_range = date_range
        self.records: List[PouringRecord] = []

    def _is_in_date_range(self, dt: Optional[datetime]) -> bool:
        if not self.date_range or not dt:
            return True
        start, end = self.date_range
        return start <= dt <= end

    def _scan_photos(self, folder_path: Path) -> List[PhotoRecord]:
        photos = []
        for root, _, files in os.walk(folder_path):
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in PHOTO_EXTENSIONS:
                    fp = os.path.join(root, f)
                    shoot_time = get_photo_datetime(fp)
                    photos.append(PhotoRecord(
                        file_path=fp, file_name=f, shoot_time=shoot_time
                    ))
        return photos

    def _parse_manifest_csv(self, csv_path: Path) -> List[dict]:
        records = []
        try:
            import pandas as pd
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            for _, row in df.iterrows():
                records.append(row.to_dict())
            return records
        except Exception as e:
            logger.debug(f"读取CSV清单失败 {csv_path}: {e}")
            try:
                with open(csv_path, encoding="gbk", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        records.append(dict(row))
            except Exception as e2:
                logger.debug(f"GBK读取也失败 {csv_path}: {e2}")
        return records

    def _parse_manifest_excel(self, excel_path: Path) -> List[dict]:
        try:
            import pandas as pd
            df = pd.read_excel(excel_path)
            records = []
            for _, row in df.iterrows():
                records.append({k: (v if pd.notna(v) else None) for k, v in row.to_dict().items()})
            return records
        except Exception as e:
            logger.debug(f"读取Excel清单失败 {excel_path}: {e}")
        return []

    def _find_manifest(self, folder_path: Path) -> Optional[Path]:
        manifest_names = ["manifest", "清单", "浇筑清单", "旁站清单", "records", "index"]
        for name in manifest_names:
            for ext in [".xlsx", ".xls", ".csv"]:
                p = folder_path / f"{name}{ext}"
                if p.exists():
                    return p
        for f in folder_path.iterdir():
            if f.is_file() and f.suffix.lower() in {".xlsx", ".xls", ".csv"}:
                stem_lower = f.stem.lower()
                if any(k in stem_lower for k in ["清单", "manifest", "record", "index"]):
                    return f
        return None

    def _read_log_fields(self, log_file: Path) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        if not log_file or not log_file.exists():
            return fields
        try:
            if log_file.suffix.lower() == ".txt":
                content = log_file.read_text(encoding="utf-8", errors="ignore")
                fields = extract_fields_from_text(content)
            elif log_file.suffix.lower() in {".xlsx", ".xls"}:
                import pandas as pd
                df = pd.read_excel(log_file, dtype=object)
                text_parts = []
                row_field_map: Dict[str, Any] = {}
                for _, row in df.iterrows():
                    row_dict = {str(k): v for k, v in row.to_dict().items() if not _is_empty(v)}
                    for k, v in row_dict.items():
                        text_parts.append(f"{k}:{v}")
                    ks = list(row_dict.keys())
                    if len(ks) >= 2:
                        for i in range(len(ks) - 1):
                            try:
                                row_field_map[str(ks[i])] = row_dict[ks[i+1]]
                            except Exception:
                                pass
                text = " ".join(text_parts)
                fields = extract_fields_from_text(text)
                if "楼栋号" in row_field_map and "building" not in fields:
                    v = str(row_field_map["楼栋号"]).strip()
                    if not _is_empty(v):
                        fields["building"] = extract_building_from_name(v) or v
                if "浇筑部位" in row_field_map and "position" not in fields:
                    v = str(row_field_map["浇筑部位"]).strip()
                    if not _is_empty(v):
                        fields["position"] = extract_position_from_name(v) or v
                if "强度等级" in row_field_map and "strength_grade" not in fields:
                    v = str(row_field_map["强度等级"]).strip()
                    if not _is_empty(v):
                        fields["strength_grade"] = extract_strength_from_name(v) or v
                if "坍落度" in row_field_map and "slump" not in fields:
                    v = str(row_field_map["坍落度"]).strip()
                    if not _is_empty(v):
                        fields["slump"] = extract_slump_from_name(v) or v
                if "试块组数" in row_field_map and "sample_count" not in fields:
                    v = str(row_field_map["试块组数"]).strip()
                    if not _is_empty(v):
                        fields["sample_count"] = extract_sample_count_from_name(v) or v
                if "监理员" in row_field_map and "supervisor" not in fields:
                    v = str(row_field_map["监理员"]).strip()
                    if not _is_empty(v):
                        fields["supervisor"] = extract_supervisor_from_name(v) or v
                if "浇筑日期" in row_field_map and "pouring_date" not in fields:
                    dt = parse_date_from_string(row_field_map["浇筑日期"])
                    if dt:
                        fields["pouring_date"] = dt
            elif log_file.suffix.lower() == ".csv":
                content = log_file.read_text(encoding="utf-8-sig", errors="ignore")
                fields = extract_fields_from_text(content)
        except Exception as e:
            logger.debug(f"读取日志字段失败 {log_file}: {e}")
        return fields

    def _find_log_file(self, folder_path: Path) -> Optional[Path]:
        log_file = None
        for f in folder_path.iterdir():
            if f.is_file() and f.suffix.lower() in LOG_EXTENSIONS:
                if "日志" in f.stem or "旁站" in f.stem or "记录" in f.stem or "log" in f.stem.lower():
                    log_file = f
                    break
        if log_file is None:
            for f in folder_path.iterdir():
                if f.is_file() and f.suffix.lower() in LOG_EXTENSIONS:
                    log_file = f
                    break
        return log_file

    def _create_record_from_folder(self, folder_path: Path) -> Optional[PouringRecord]:
        folder_name = folder_path.name
        record_id = folder_name

        log_file = self._find_log_file(folder_path)
        log_fields = self._read_log_fields(log_file) if log_file else {}

        f_date = extract_date_from_filename(folder_name)
        f_building = extract_building_from_name(folder_name)
        f_position = extract_position_from_name(folder_name)
        f_strength = extract_strength_from_name(folder_name)
        f_slump = extract_slump_from_name(folder_name)
        f_sample_count = extract_sample_count_from_name(folder_name)
        f_supervisor = extract_supervisor_from_name(folder_name)

        photos = self._scan_photos(folder_path)

        def _pick(field_name, f_val, log_val=None):
            if log_val is not None and not _is_empty(log_val):
                return str(log_val).strip()
            if f_val is not None and not _is_empty(f_val):
                if isinstance(f_val, datetime):
                    return f_val
                return str(f_val).strip()
            return None

        building = _pick("building", f_building, log_fields.get("building"))
        position = _pick("position", f_position, log_fields.get("position"))
        strength = _pick("strength_grade", f_strength, log_fields.get("strength_grade"))
        slump = _pick("slump", f_slump, log_fields.get("slump"))
        sample_count = _pick("sample_count", f_sample_count, log_fields.get("sample_count"))
        supervisor = _pick("supervisor", f_supervisor, log_fields.get("supervisor"))
        pouring_date = f_date
        if log_fields.get("pouring_date"):
            pouring_date = log_fields["pouring_date"]

        has_sign = log_fields.get("has_supervisor_sign", False)

        record = PouringRecord(
            record_id=record_id,
            log_file_path=str(log_file) if log_file else None,
            log_file_name=log_file.name if log_file else None,
            project_name=self.project_dir.name,
            building=building or "",
            pouring_date=pouring_date,
            position=position,
            strength_grade=strength,
            slump=slump,
            sample_count=sample_count,
            supervisor=supervisor,
            has_supervisor_sign=has_sign,
            photos=photos,
        )

        def _str_or_none(v):
            if v is None or _is_empty(v):
                return None
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%d")
            return str(v).strip()

        record.source_building = FieldSource(
            folder=_str_or_none(f_building),
            log=_str_or_none(log_fields.get("building")),
        )
        record.source_position = FieldSource(
            folder=_str_or_none(f_position),
            log=_str_or_none(log_fields.get("position")),
        )
        record.source_strength = FieldSource(
            folder=_str_or_none(f_strength),
            log=_str_or_none(log_fields.get("strength_grade")),
        )
        record.source_supervisor = FieldSource(
            folder=_str_or_none(f_supervisor),
            log=_str_or_none(log_fields.get("supervisor")),
        )
        record.source_date = FieldSource(
            folder=_str_or_none(f_date),
            log=_str_or_none(log_fields.get("pouring_date")),
        )
        return record

    def _apply_manifest(self, record: PouringRecord, manifest_row: dict) -> PouringRecord:
        field_mapping = {
            "浇筑部位": "position",
            "部位": "position",
            "强度等级": "strength_grade",
            "强度": "strength_grade",
            "坍落度": "slump",
            "试块组数": "sample_count",
            "试块": "sample_count",
            "监理员": "supervisor",
            "监理": "supervisor",
            "旁站人员": "supervisor",
            "楼栋号": "building",
            "楼栋": "building",
            "楼号": "building",
            "浇筑日期": "pouring_date",
            "日期": "pouring_date",
            "项目名称": "project_name",
        }

        def _str_or_none(v):
            if v is None or _is_empty(v):
                return None
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%d")
            return str(v).strip()

        manifest_values: Dict[str, Any] = {}
        for csv_key, attr in field_mapping.items():
            for k, v in manifest_row.items():
                if str(k).strip() == csv_key:
                    if _is_empty(v):
                        continue
                    if attr == "pouring_date":
                        parsed = parse_date_from_string(str(v))
                        if parsed:
                            manifest_values[attr] = parsed
                    else:
                        manifest_values[attr] = str(v).strip()

        for attr, val in manifest_values.items():
            if attr == "pouring_date":
                if record.pouring_date is None:
                    record.pouring_date = val
            else:
                cur = getattr(record, attr)
                if cur is None or _is_empty(cur):
                    setattr(record, attr, str(val).strip())

        if "position" in manifest_values:
            record.source_position.manifest = _str_or_none(manifest_values["position"])
        if "strength_grade" in manifest_values:
            record.source_strength.manifest = _str_or_none(manifest_values["strength_grade"])
        if "supervisor" in manifest_values:
            record.source_supervisor.manifest = _str_or_none(manifest_values["supervisor"])
        if "building" in manifest_values:
            bv = manifest_values["building"]
            bld = extract_building_from_name(str(bv)) or str(bv)
            record.source_building.manifest = _str_or_none(bld)
            if _is_empty(record.building):
                record.building = bld
        if "pouring_date" in manifest_values:
            record.source_date.manifest = _str_or_none(manifest_values["pouring_date"])

        sign_key = None
        for k in manifest_row.keys():
            kl = str(k).strip()
            if "签名" in kl or "签字" in kl:
                sign_key = k
                break
        if sign_key:
            v = manifest_row[sign_key]
            if not _is_empty(v) and str(v).strip() not in ("", "无", "否", "0", "未签"):
                if not record.has_supervisor_sign:
                    record.has_supervisor_sign = True
            elif not _is_empty(v) and str(v).strip() in ("无", "否", "0", "未签"):
                record.has_supervisor_sign = False

        return record

    def _match_manifest_to_record(self, manifest_row: dict, records: List[PouringRecord]) -> Optional[PouringRecord]:
        row_date = None
        row_building = ""
        row_position = ""
        row_strength = ""
        for k, v in manifest_row.items():
            kl = str(k).strip()
            v_str = "" if _is_empty(v) else str(v).strip()
            if "日期" in kl:
                row_date = parse_date_from_string(v_str)
            if "楼栋" in kl or "楼号" in kl:
                row_building = extract_building_from_name(v_str) or v_str
            if "部位" in kl:
                row_position = v_str
            if "强度" in kl:
                row_strength = extract_strength_from_name(v_str) or v_str

        def _norm_building(b):
            return str(b).replace("号楼", "").replace("#", "").replace(" ", "").strip()

        def _norm_strength(s):
            return str(s).upper().replace(" ", "").strip()

        def _norm_position(p):
            return str(p).replace(" ", "").strip()

        candidates = []
        for r in records:
            score = 0
            detail = []
            if row_date and r.pouring_date and row_date.date() == r.pouring_date.date():
                score += 3
                detail.append("日期")
            if row_building and r.building:
                if _norm_building(row_building) == _norm_building(r.building):
                    score += 3
                    detail.append("楼栋")
            if row_position and r.position:
                rp = _norm_position(row_position)
                lp = _norm_position(r.position)
                if rp and lp and (rp in lp or lp in rp):
                    score += 2
                    detail.append("部位")
            if row_strength and r.strength_grade:
                if _norm_strength(row_strength) == _norm_strength(r.strength_grade):
                    score += 2
                    detail.append("强度")
            if score >= 4:
                candidates.append((score, r, detail))

        if not candidates:
            return None

        candidates.sort(key=lambda x: -x[0])
        best_score = candidates[0][0]
        best_candidates = [c for c in candidates if c[0] == best_score]

        if len(best_candidates) > 1 and best_score < 8:
            return None

        return best_candidates[0][1]

    def scan(self) -> List[PouringRecord]:
        self.records = []

        manifest = None
        manifest_path = self._find_manifest(self.project_dir)
        if manifest_path:
            if manifest_path.suffix.lower() == ".csv":
                manifest = self._parse_manifest_csv(manifest_path)
            else:
                manifest = self._parse_manifest_excel(manifest_path)

        for item in self.project_dir.iterdir():
            if item.is_dir():
                record = self._create_record_from_folder(item)
                if record:
                    self.records.append(record)

        if manifest:
            matched_ids = set()
            for row in manifest:
                matched = self._match_manifest_to_record(row, self.records)
                if matched:
                    self._apply_manifest(matched, row)
                    matched_ids.add(matched.record_id)
                else:
                    row_date = None
                    row_building = ""
                    row_position_val = ""
                    row_strength_val = ""
                    for k, v in row.items():
                        kl = str(k).strip()
                        v_str = "" if _is_empty(v) else str(v).strip()
                        if "日期" in kl:
                            row_date = parse_date_from_string(v_str)
                        if "楼栋" in kl or "楼号" in kl:
                            row_building = extract_building_from_name(v_str) or v_str
                        if "部位" in kl:
                            row_position_val = v_str
                        if "强度" in kl:
                            row_strength_val = v_str
                    rec = PouringRecord(
                        record_id=f"未匹配清单-{len(self.records)+1}",
                        project_name=self.project_dir.name,
                        building=row_building,
                        pouring_date=row_date,
                        is_manifest_only=True,
                        manifest_unmatched=True,
                    )
                    if row_position_val:
                        pos = extract_position_from_name(row_position_val) or row_position_val
                        rec.position = pos
                        rec.source_position.manifest = pos
                    if row_strength_val:
                        st = extract_strength_from_name(row_strength_val) or row_strength_val
                        rec.strength_grade = st
                        rec.source_strength.manifest = st
                    self._apply_manifest(rec, row)
                    self.records.append(rec)

        filtered = []
        for r in self.records:
            if self._is_in_date_range(r.pouring_date):
                filtered.append(r)
        self.records = filtered

        self.records.sort(key=lambda r: (r.pouring_date or datetime.min, r.building, r.record_id))
        return self.records
