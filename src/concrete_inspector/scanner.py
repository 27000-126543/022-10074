import os
import re
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import logging

from PIL import Image
from PIL.ExifTags import TAGS

from .models import PouringRecord, PhotoRecord

logger = logging.getLogger(__name__)


DATE_PATTERNS = [
    re.compile(r"(\d{4})[-_年\.](\d{1,2})[-_月\.](\d{1,2})"),
    re.compile(r"(\d{4})(\d{2})(\d{2})"),
    re.compile(r"(\d{2})[-_年\.](\d{1,2})[-_月\.](\d{1,2})"),
]

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}
LOG_EXTENSIONS = {".xlsx", ".xls", ".csv", ".txt", ".docx", ".doc"}


def parse_date_from_string(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
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
        r"(\d+层[一二三四五六七八九十百千万]*[梁板柱墙基承台基础]?)",
        r"([一二三四五六七八九十百千万]+层[梁板柱墙基承台基础]?)",
        r"(\d+F\s*[梁板柱墙]?)",
    ]
    for p in patterns:
        m = re.search(p, name)
        if m:
            return m.group(1)
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
    mtime = os.path.getmtime(file_path)
    return datetime.fromtimestamp(mtime)


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
                records.append({k: (v if pd.notna(v) else "") for k, v in row.to_dict().items()})
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

    def _create_record_from_folder(self, folder_path: Path) -> Optional[PouringRecord]:
        folder_name = folder_path.name
        record_id = folder_name

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

        pouring_date = extract_date_from_filename(folder_name)
        building = extract_building_from_name(folder_name)
        position = extract_position_from_name(folder_name)
        strength_grade = extract_strength_from_name(folder_name)
        slump = extract_slump_from_name(folder_name)
        sample_count = extract_sample_count_from_name(folder_name)
        supervisor = extract_supervisor_from_name(folder_name)

        photos = self._scan_photos(folder_path)

        record = PouringRecord(
            record_id=record_id,
            log_file_path=str(log_file) if log_file else None,
            log_file_name=log_file.name if log_file else None,
            project_name=self.project_dir.name,
            building=building,
            pouring_date=pouring_date,
            position=position,
            strength_grade=strength_grade,
            slump=slump,
            sample_count=sample_count,
            supervisor=supervisor,
            photos=photos,
        )

        has_sign = False
        if log_file and log_file.suffix.lower() in {".xlsx", ".xls", ".csv", ".txt"}:
            try:
                content_text = ""
                if log_file.suffix.lower() == ".txt":
                    content_text = log_file.read_text(encoding="utf-8", errors="ignore")
                elif log_file.suffix.lower() in {".xlsx", ".xls"}:
                    import pandas as pd
                    df = pd.read_excel(log_file)
                    content_text = " ".join([str(v) for v in df.values.flatten()])
                elif log_file.suffix.lower() == ".csv":
                    content_text = log_file.read_text(encoding="utf-8-sig", errors="ignore")

                if content_text:
                    import re as _re
                    signed_patterns = [
                        r"监理员?签名[:：]?\s*[\u4e00-\u9fa5]{2,4}(?!\s*[_—]+)",
                        r"签名[:：]?\s*[\u4e00-\u9fa5]{2,4}(?!\s*[_—]+)",
                        r"签字[:：]?\s*[\u4e00-\u9fa5]{2,4}(?!\s*[_—]+)",
                        r"[\u4e00-\u9fa5]{2,4}\s*[（(]\s*已签\s*[)）]",
                    ]
                    for pat in signed_patterns:
                        if _re.search(pat, content_text):
                            has_sign = True
                            break

                    if not has_sign and supervisor:
                        m = _re.search(r"签名[:：]\s*" + _re.escape(supervisor), content_text)
                        if m:
                            suffix = content_text[m.end():m.end()+5]
                            if not _re.match(r"\s*[_—]{2,}", suffix):
                                has_sign = True

                        if not has_sign:
                            pattern = _re.escape(supervisor) + r"\s*[（(]\s*已签"
                            if _re.search(pattern, content_text):
                                has_sign = True
            except Exception as e:
                logger.debug(f"检查签名失败 {log_file}: {e}")
        record.has_supervisor_sign = has_sign

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

        def _is_empty(v) -> bool:
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

        for csv_key, attr in field_mapping.items():
            for k, v in manifest_row.items():
                if str(k).strip() == csv_key:
                    if _is_empty(v):
                        continue
                    if attr == "pouring_date":
                        parsed = parse_date_from_string(str(v))
                        if parsed and record.pouring_date is None:
                            record.pouring_date = parsed
                    else:
                        v_str = str(v).strip()
                        current_val = getattr(record, attr)
                        if current_val in (None, "") or _is_empty(current_val):
                            setattr(record, attr, v_str)

        sign_key = None
        for k in manifest_row.keys():
            kl = str(k).strip()
            if "签名" in kl or "签字" in kl:
                sign_key = k
                break
        if sign_key:
            v = manifest_row[sign_key]
            if not _is_empty(v) and str(v).strip() not in ("", "无", "否", "0"):
                record.has_supervisor_sign = True
            elif _is_empty(v):
                pass
            else:
                if str(v).strip() in ("", "无", "否", "0"):
                    record.has_supervisor_sign = False

        return record

    def _match_manifest_to_record(self, manifest_row: dict, records: List[PouringRecord]) -> Optional[PouringRecord]:
        row_date = None
        row_building = ""
        row_position = ""
        for k, v in manifest_row.items():
            kl = str(k).strip()
            v_str = str(v).strip() if v else ""
            if "日期" in kl:
                row_date = parse_date_from_string(v_str)
            if "楼栋" in kl or "楼号" in kl:
                row_building = extract_building_from_name(v_str) or v_str
            if "部位" in kl:
                row_position = v_str

        candidates = []
        for r in records:
            score = 0
            if row_date and r.pouring_date and row_date.date() == r.pouring_date.date():
                score += 3
            if row_building and r.building and row_building == r.building:
                score += 2
            if row_position and r.position and row_position in r.position:
                score += 2
            if score >= 3:
                candidates.append((score, r))

        if candidates:
            candidates.sort(key=lambda x: -x[0])
            return candidates[0][1]
        return None

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
                    if self._is_in_date_range(record.pouring_date):
                        self.records.append(record)
            elif item.is_file() and manifest is None:
                if item.suffix.lower() in {".xlsx", ".xls", ".csv"}:
                    if item.stem == manifest_path.stem if manifest_path else True:
                        continue

        if manifest:
            for row in manifest:
                matched = self._match_manifest_to_record(row, self.records)
                if matched:
                    self._apply_manifest(matched, row)
                else:
                    row_date = None
                    row_building = ""
                    for k, v in row.items():
                        kl = str(k).strip()
                        v_str = str(v).strip() if v else ""
                        if "日期" in kl:
                            row_date = parse_date_from_string(v_str)
                        if "楼栋" in kl or "楼号" in kl:
                            row_building = extract_building_from_name(v_str) or v_str
                    if self._is_in_date_range(row_date):
                        rec = PouringRecord(
                            record_id=f"清单-{len(self.records)+1}",
                            project_name=self.project_dir.name,
                            building=row_building,
                            pouring_date=row_date,
                        )
                        self._apply_manifest(rec, row)
                        self.records.append(rec)

        self.records.sort(key=lambda r: (r.pouring_date or datetime.min, r.building, r.record_id))
        return self.records
