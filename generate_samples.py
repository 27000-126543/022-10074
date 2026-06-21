"""生成示例旁站数据（含一致性冲突场景），用于测试工具功能"""
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
        mtime = shoot_time.timestamp()
        os.utime(filepath, (mtime, mtime))
        return
    try:
        img = Image.new('RGB', (100, 100), color='lightblue')
        from PIL.ExifTags import TAGS
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


def create_log_txt(filepath: Path, record: dict, with_sign: bool, override: dict = None):
    """override: 指定日志与文件夹/清单不同的字段，用于制造一致性冲突"""
    ov = override or {}
    bld = ov.get("building", record['building'])
    pos = ov.get("position", record['position_full'])
    stg = ov.get("strength", record['strength'])
    slp = ov.get("slump", record.get('slump'))
    sc = ov.get("sample_count", record.get('sample_count'))
    sup = ov.get("supervisor", record['supervisor'])
    dt = ov.get("pouring_date", record['date'])

    lines = [
        f"混凝土浇筑旁站监理日志",
        f"项目名称：阳光花园二期",
        f"楼栋号：{bld}",
        f"浇筑日期：{dt.strftime('%Y年%m月%d日')}",
        f"浇筑部位：{pos}",
        f"强度等级：{stg}",
    ]
    if slp:
        lines.append(f"坍落度：{slp}")
    if sc:
        lines.append(f"试块组数：{sc} 组")
    lines.append(f"旁站监理员：{sup}")
    if with_sign:
        lines.append(f"监理签名：{sup}（已签）")
    else:
        lines.append(f"监理签名：___________")
    lines.append("")
    lines.append("旁站过程记录：...")
    filepath.write_text("\n".join(lines), encoding="utf-8")


def create_manifest(records, csv_path: Path):
    headers = [
        "序号", "浇筑日期", "楼栋号", "浇筑部位", "强度等级",
        "坍落度", "试块组数", "监理员", "监理签名", "备注"
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for i, r in enumerate(records, 1):
            ov = r.get("manifest_override", {})
            writer.writerow({
                "序号": i,
                "浇筑日期": ov.get("pouring_date", r['date']).strftime("%Y-%m-%d"),
                "楼栋号": ov.get("building", r['building']),
                "浇筑部位": ov.get("position_full", r['position_full']),
                "强度等级": ov.get("strength", r['strength']),
                "坍落度": ov.get("slump", r.get('slump', '')),
                "试块组数": ov.get("sample_count", r.get('sample_count', '')),
                "监理员": ov.get("supervisor", r['supervisor']),
                "监理签名": "已签" if ov.get("with_sign", r.get('with_sign')) else "",
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
        {"variant": "conflict_position", "notes": "一致性冲突-部位不一致"},
        {"variant": "conflict_supervisor", "notes": "一致性冲突-监理员不一致"},
        {"variant": "conflict_strength", "notes": "一致性冲突-强度等级不一致"},
        {"variant": "conflict_building", "notes": "一致性冲突-楼栋不一致"},
        {"variant": "photo_early", "notes": "照片时间早于浇筑3天"},
    ]

    for i, sample in enumerate(samples):
        variant = sample["variant"]
        dt = random_date_2024_jan()
        building = random.choice(BUILDINGS)
        pos_level, pos_type = random.choice(POSITIONS)
        position_full = f"{pos_level}{pos_type}"
        strength = random.choice(STRENGTHS)
        slump = "160±20mm"
        sample_count = str(random.randint(2, 5))
        supervisor = random.choice(SUPERVISORS)
        with_sign = True
        photo_count = random.randint(3, 6)
        include_log = True
        include_folder = True
        folder_omit_pos = False
        folder_omit_strength = False
        folder_omit_slump = False
        folder_omit_sample = False
        log_override = {}
        manifest_override = {}
        photo_day_offset = 0

        if variant == "perfect":
            pass
        elif variant == "missing_position":
            folder_omit_pos = True
            slump = ""
        elif variant == "missing_strength":
            folder_omit_strength = True
        elif variant == "missing_slump":
            folder_omit_slump = True
            slump = ""
        elif variant == "missing_sample_count":
            folder_omit_sample = True
            sample_count = ""
        elif variant == "missing_sign":
            with_sign = False
        elif variant == "missing_photo":
            photo_count = 1
        elif variant == "missing_log":
            include_log = False
        elif variant == "multiple_missing":
            folder_omit_pos = True
            folder_omit_slump = True
            slump = ""
            sample_count = ""
            with_sign = False
            photo_count = 1
        elif variant == "manifest_only":
            include_folder = False
        elif variant == "conflict_position":
            log_override = {"position": f"修改后{pos_level}梁板（日志笔误版）"}
            manifest_override = {"position_full": f"清单版{pos_level}{pos_type}"}
        elif variant == "conflict_supervisor":
            other = [s for s in SUPERVISORS if s != supervisor]
            log_override = {"supervisor": random.choice(other)}
        elif variant == "conflict_strength":
            other = [s for s in STRENGTHS if s != strength]
            log_override = {"strength": random.choice(other)}
        elif variant == "conflict_building":
            other = [b for b in BUILDINGS if b != building]
            manifest_override = {"building": random.choice(other)}
        elif variant == "photo_early":
            photo_day_offset = -3

        folder_name_parts = [dt.strftime("%Y%m%d"), building]
        if not folder_omit_pos:
            folder_name_parts.append(pos_level + pos_type)
        if not folder_omit_strength:
            folder_name_parts.append(strength)
        folder_name = "_".join(folder_name_parts)
        folder_name += f"({sample['notes']})"

        rec = {
            "date": dt,
            "building": building,
            "position_full": position_full,
            "pos_level": pos_level,
            "pos_type": pos_type,
            "strength": strength,
            "slump": "" if folder_omit_slump else slump,
            "sample_count": "" if folder_omit_sample else sample_count,
            "supervisor": supervisor,
            "with_sign": with_sign,
            "photo_count": photo_count,
            "include_log": include_log,
            "include_folder": include_folder,
            "note": sample['notes'],
            "folder_name": folder_name,
            "log_override": log_override,
            "manifest_override": manifest_override,
            "photo_day_offset": photo_day_offset,
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
        if rec["photo_day_offset"]:
            base_time = base_time + timedelta(days=rec["photo_day_offset"])
        for p in range(rec["photo_count"]):
            fname = f"IMG_{rec['date'].strftime('%Y%m%d')}_{p+1:03d}.jpg"
            fpath = photos_dir / fname
            shoot_t = base_time + timedelta(minutes=p * random.randint(30, 90))
            create_fake_image(fpath, shoot_t)

        if rec["include_log"]:
            log_name = f"{rec['building']}_{rec['date'].strftime('%Y%m%d')}_旁站日志.txt"
            log_path = folder / log_name
            eff_pos = rec["pos_level"] + rec["pos_type"]
            r2 = dict(rec)
            r2["position_full"] = eff_pos
            create_log_txt(log_path, r2, rec["with_sign"], override=rec.get("log_override"))

    manifest_path = BASE_DIR / "浇筑清单.csv"
    create_manifest(records_data, manifest_path)

    print(f"✅ 示例数据已生成到：{BASE_DIR}")
    print(f"   共 {len(records_data)} 条记录，其中 {sum(1 for r in records_data if r['include_folder'])} 个文件夹")
    print()
    print("示例场景说明：")
    for i, rec in enumerate(records_data, 1):
        note = rec.get("note", "")
        print(f"  {i:>2}. {note}")
    print()

    try:
        from concrete_inspector.rules import generate_sample_rules
        rules_path = BASE_DIR / "inspection_rules.json"
        generate_sample_rules(str(rules_path))
        print("✅ 已生成项目规则配置文件：", rules_path)
    except Exception as e:
        print(f"⚠️  生成规则文件失败：{e}")

    print()
    print("下一步命令示例：")
    print(f"  cd {BASE_DIR.parent}")
    print(f"  python -m concrete_inspector init-rules -o 项目A_rules.json  # 生成自定义规则")
    print(f"  python -m concrete_inspector check -p 示例项目_阳光花园二期 -s 2024-01-01 -e 2024-01-31 --format all")
    print(f"  python -m concrete_inspector filter -p 示例项目_阳光花园二期 --consistency-only")
    print(f"  python -m concrete_inspector list -p 示例项目_阳光花园二期 -o ./reports --format csv")
    print(f"  python -m concrete_inspector info -p 示例项目_阳光花园二期")


if __name__ == "__main__":
    random.seed(42)
    generate_samples()
