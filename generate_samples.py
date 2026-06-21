"""生成示例旁站数据，用于测试工具功能"""
import os
import csv
from datetime import datetime, timedelta
from pathlib import Path
import random


try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


BASE_DIR = Path(__file__).parent / "示例项目_阳光花园二期"
BASE_DIR.mkdir(exist_ok=True)


BUILDINGS = ["1号楼", "2号楼", "3号楼", "5号楼"]
SUPERVISORS = ["张三", "李四", "王五", "赵六"]
POSITIONS = [
    ("一层", "梁板柱"),
    ("二层", "梁板"),
    ("三层", "柱墙"),
    ("四层", "梁板柱"),
    ("五层", "基础承台"),
    ("地下室负一层", "墙板"),
]
STRENGTHS = ["C30", "C35", "C40", "C45", "C30P6"]


def random_date_2024_jan():
    start = datetime(2024, 1, 2)
    end = datetime(2024, 1, 28)
    delta_days = random.randint(0, (end - start).days)
    return start + timedelta(days=delta_days)


def create_fake_image(filepath: Path, shoot_time: datetime):
    if not HAS_PIL:
        filepath.touch()
        return
    try:
        img = Image.new('RGB', (100, 100), color='lightblue')
        from PIL.ExifTags import TAGS, GPSTAGS
        exif = img.getexif()
        dt_str = shoot_time.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = dt_str
        exif[0x9003] = dt_str
        exif[0x9004] = dt_str
        img.save(filepath, "JPEG", exif=exif)
        mtime = shoot_time.timestamp()
        os.utime(filepath, (mtime, mtime))
    except Exception:
        filepath.touch()


def create_log_txt(filepath: Path, record: dict, with_sign: bool):
    lines = [
        f"混凝土浇筑旁站监理日志",
        f"项目名称：阳光花园二期",
        f"楼栋号：{record['building']}",
        f"浇筑日期：{record['date'].strftime('%Y年%m月%d日')}",
        f"浇筑部位：{record['position']}",
        f"强度等级：{record['strength']}",
    ]
    if record.get('slump'):
        lines.append(f"坍落度：{record['slump']}")
    if record.get('sample_count'):
        lines.append(f"试块组数：{record['sample_count']} 组")
    lines.append(f"旁站监理员：{record['supervisor']}")
    if with_sign:
        lines.append(f"监理签名：{record['supervisor']}（已签）")
    else:
        lines.append(f"监理签名：___________")
    lines.append("")
    lines.append("旁站过程记录：...")
    filepath.write_text("\n".join(lines), encoding="utf-8")


def create_manifest_csv(records, csv_path: Path):
    headers = [
        "序号", "浇筑日期", "楼栋号", "浇筑部位", "强度等级",
        "坍落度", "试块组数", "监理员", "监理签名", "备注"
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for i, r in enumerate(records, 1):
            writer.writerow({
                "序号": i,
                "浇筑日期": r['date'].strftime("%Y-%m-%d"),
                "楼栋号": r['building'],
                "浇筑部位": r['position'],
                "强度等级": r['strength'],
                "坍落度": r.get('slump', ''),
                "试块组数": r.get('sample_count', ''),
                "监理员": r['supervisor'],
                "监理签名": "已签" if r.get('with_sign') else "",
                "备注": r.get('note', ''),
            })


def generate_samples():
    records_data = []

    samples = [
        {"variant": "perfect", "notes": "完整无缺项"},
        {"variant": "missing_position", "notes": "缺少部位"},
        {"variant": "missing_strength", "notes": "缺少强度等级"},
        {"variant": "missing_slump", "notes": "缺少坍落度"},
        {"variant": "missing_sample_count", "notes": "缺少试块组数"},
        {"variant": "missing_sign", "notes": "缺少监理签名"},
        {"variant": "missing_photo", "notes": "照片不足"},
        {"variant": "missing_log", "notes": "缺少日志文件"},
        {"variant": "multiple_missing", "notes": "多字段缺失"},
        {"variant": "manifest_only", "notes": "仅清单记录，无文件夹"},
    ]

    for i, sample in enumerate(samples):
        variant = sample["variant"]
        dt = random_date_2024_jan()
        building = random.choice(BUILDINGS)
        pos_level, pos_type = random.choice(POSITIONS)
        position = f"{building} {pos_level}{pos_type}"
        strength = random.choice(STRENGTHS)
        slump = "160±20mm"
        sample_count = str(random.randint(2, 5))
        supervisor = random.choice(SUPERVISORS)
        with_sign = True
        photo_count = random.randint(3, 6)
        include_log = True
        include_folder = True
        photo_time_gap_ok = True

        if variant == "perfect":
            pass
        elif variant == "missing_position":
            position = ""
        elif variant == "missing_strength":
            strength = ""
        elif variant == "missing_slump":
            slump = ""
        elif variant == "missing_sample_count":
            sample_count = ""
        elif variant == "missing_sign":
            with_sign = False
        elif variant == "missing_photo":
            photo_count = 1
        elif variant == "missing_log":
            include_log = False
        elif variant == "multiple_missing":
            position = ""
            slump = ""
            with_sign = False
            photo_count = 1
        elif variant == "manifest_only":
            include_folder = False

        folder_name_parts = [dt.strftime("%Y%m%d"), building]
        if position:
            folder_name_parts.append(pos_level + pos_type)
        if strength:
            folder_name_parts.append(strength)
        folder_name = "_".join(folder_name_parts)
        folder_name += f"({sample['notes']})"

        rec = {
            "date": dt,
            "building": building,
            "position": position,
            "strength": strength,
            "slump": slump,
            "sample_count": sample_count,
            "supervisor": supervisor,
            "with_sign": with_sign,
            "photo_count": photo_count,
            "include_log": include_log,
            "include_folder": include_folder,
            "note": sample['notes'],
            "folder_name": folder_name,
        }
        records_data.append(rec)

    for rec in records_data:
        if not rec["include_folder"]:
            continue

        folder = BASE_DIR / rec["folder_name"]
        folder.mkdir(exist_ok=True)

        photos_dir = folder / "照片"
        photos_dir.mkdir(exist_ok=True)
        base_time = rec["date"].replace(hour=8, minute=30)
        for p in range(rec["photo_count"]):
            fname = f"IMG_{rec['date'].strftime('%Y%m%d')}_{p+1:03d}.jpg"
            fpath = photos_dir / fname
            shoot_t = base_time + timedelta(minutes=p * random.randint(30, 90))
            create_fake_image(fpath, shoot_t)

        if rec["include_log"]:
            log_name = f"{rec['building']}_{rec['date'].strftime('%Y%m%d')}_旁站日志.txt"
            log_path = folder / log_name
            create_log_txt(log_path, rec, rec["with_sign"])

    manifest_path = BASE_DIR / "浇筑清单.csv"
    create_manifest_csv(records_data, manifest_path)

    print(f"✅ 示例数据已生成到：{BASE_DIR}")
    print(f"   共 {len(records_data)} 条记录，其中 {sum(1 for r in records_data if r['include_folder'])} 个文件夹")
    print()
    print("示例场景说明：")
    variants_desc = {
        "perfect": "完整无缺项（合格）",
        "missing_position": "缺少部位（严重）",
        "missing_strength": "缺少强度等级（严重）",
        "missing_slump": "缺少坍落度（重要）",
        "missing_sample_count": "缺少试块组数（重要）",
        "missing_sign": "缺少监理签名（严重）",
        "missing_photo": "照片数量不足（一般）",
        "missing_log": "缺少旁站日志（重要）",
        "multiple_missing": "多字段同时缺失",
        "manifest_only": "仅清单有记录，无实际文件夹",
    }
    for i, rec in enumerate(records_data, 1):
        note = rec.get("note", "")
        print(f"  {i:>2}. {note}")
    print()
    print("下一步命令示例：")
    print(f"  cd {BASE_DIR.parent}")
    print(f"  python -m concrete_inspector check -p 示例项目_阳光花园二期 -s 2024-01-01 -e 2024-01-31")
    print(f"  python -m concrete_inspector filter -p 示例项目_阳光花园二期 --severity critical")
    print(f"  python -m concrete_inspector list -p 示例项目_阳光花园二期 -o ./reports")


if __name__ == "__main__":
    random.seed(42)
    generate_samples()
