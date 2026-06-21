import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

import click

from . import __version__
from .scanner import DirectoryScanner, parse_date_from_string
from .validator import RecordValidator, get_statistics
from .filters import RecordFilter
from .reporter import ReportGenerator
from .models import Severity, IssueType
from .rules import load_rules, generate_sample_rules, InspectionRules, ISSUE_TYPE_TO_KEY


def _fix_console_encoding():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


_fix_console_encoding()


logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_date_range(start: Optional[str], end: Optional[str]) -> Optional[Tuple[datetime, datetime]]:
    s = parse_date_from_string(start) if start else None
    e = parse_date_from_string(end) if end else None
    if e:
        e = e.replace(hour=23, minute=59, second=59)
    if s or e:
        return (s or datetime.min, e or datetime.max)
    return None


def _load_verbose_rules(project_dir: Optional[str], config_path: Optional[str], verbose: bool) -> InspectionRules:
    rules = load_rules(project_dir, config_path)
    if verbose or True:
        if rules.source_file:
            click.echo(f"⚙️  已加载规则配置：{rules.source_file}")
        else:
            click.echo("ℹ️  未找到规则配置文件，使用默认规则（可用 --rules 指定或在项目目录放 inspection_rules.json）")
    click.echo(
        f"   最少照片：{rules.min_photo_count}张 | "
        f"时间间隔≤{rules.max_photo_gap_hours}h | "
        f"照片时间：提前≤{rules.photo_early_days}天，滞后≤{rules.photo_late_days}天 | "
        f"一致性核对：{'开' if rules.consistency_check else '关'}"
    )
    return rules


def common_params(func):
    decorators = [
        click.option("--project-dir", "-p", type=click.Path(exists=True, file_okay=False, path_type=str),
                     required=True, help="项目根目录（包含各浇筑记录子文件夹）"),
        click.option("--start-date", "-s", type=str, default=None,
                     help="检查范围起始日期（按最终识别的浇筑日期过滤），如 2024-01-01"),
        click.option("--end-date", "-e", type=str, default=None,
                     help="检查范围结束日期，如 2024-01-31"),
        click.option("--output-dir", "-o", type=click.Path(file_okay=False, path_type=str),
                     default=None, help="报告输出目录（默认为当前目录）"),
        click.option("--rules", "-r", "rules_path", type=click.Path(exists=True, dir_okay=False, path_type=str),
                     default=None, help="规则配置文件路径（JSON），默认从项目目录自动查找"),
        click.option("--verbose", "-v", is_flag=True, default=False, help="显示详细日志"),
    ]
    for d in reversed(decorators):
        func = d(func)
    return func


def load_and_validate(project_dir: str, start_date: Optional[str], end_date: Optional[str],
                      verbose: bool, rules_path: Optional[str] = None):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    click.echo(f"📂 正在扫描项目目录：{project_dir}")
    date_range = parse_date_range(start_date, end_date)
    if date_range:
        s, e = date_range
        click.echo(f"📅 日期过滤范围：{s.strftime('%Y-%m-%d')} ~ {e.strftime('%Y-%m-%d')}（按最终识别的浇筑日期严格过滤）")

    rules = _load_verbose_rules(project_dir, rules_path, verbose)

    scanner = DirectoryScanner(project_dir, date_range=date_range)
    records = scanner.scan()
    click.echo(f"✅ 扫描+日期过滤后，共 {len(records)} 条记录进入检查范围")

    validator = RecordValidator(rules=rules)
    validator.validate_all(records)

    with_issues = [r for r in records if r.has_issues]
    click.echo(f"🔍 校验完成，其中 {len(with_issues)} 条记录存在问题")
    return records, rules


@click.group()
@click.version_option(version=__version__, prog_name="concrete-inspector")
@click.help_option("-h", "--help")
def main():
    """混凝土浇筑旁站批量检查工具（每周固定抽查版）

    核心命令：
      check    批量核对（默认）
      filter   问题筛选
      list     清单生成
      info     项目概览
      init-rules 生成示例规则配置文件

    规则配置文件：将 inspection_rules.json 放在项目目录下即可自动加载，
    可自定义最少照片数、时间跨度阈值、必填字段严重程度、整改建议、责任人等。
    """
    pass


@main.command("init-rules")
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=str),
              default="inspection_rules.json", help="输出的规则配置文件名")
def cmd_init_rules(output):
    """在当前目录生成一份可编辑的示例规则配置文件"""
    generate_sample_rules(output)
    click.echo("💡 编辑后放到项目目录下，运行 check/filter/list 时会自动加载。")
    click.echo("   也可以用 --rules path/to/rules.json 手动指定。")


@main.command("check")
@common_params
@click.option("--show-all", is_flag=True, default=False, help="显示全部记录（包括合格的）")
@click.option("--format", "fmt", type=click.Choice(["table", "txt", "excel", "csv", "all"]), default="table",
              help="输出格式：table控制台 / txt / excel / csv整改单 / all")
def cmd_check(project_dir, start_date, end_date, output_dir, verbose, rules_path, show_all, fmt):
    """批量核对：按项目规则检查必填字段、照片、签名和资料一致性"""
    records, rules = load_and_validate(project_dir, start_date, end_date, verbose, rules_path)
    reporter = ReportGenerator(output_dir, rules=rules)

    stats = get_statistics(records)
    click.echo("")
    click.echo(reporter.generate_statistics_report(records))

    if fmt in ("table", "txt", "excel", "csv", "all"):
        click.echo("📌 检查结果概览：")
        click.echo(reporter.generate_summary_table(records, show_all=show_all))
        click.echo("")
        click.echo("🔗 资料一致性核对：")
        click.echo(reporter.generate_consistency_table(records))

    if fmt in ("txt", "all"):
        path = reporter.save_text_report(records)
        click.echo(f"\n💾 已生成TXT报告：{path}")

    if fmt in ("excel", "all"):
        path = reporter.save_excel_report(records)
        if path:
            click.echo(f"💾 已生成Excel报告：{path}")

    if fmt in ("csv", "all"):
        path = reporter.save_action_csv(records)
        if path:
            click.echo(f"💾 已生成整改清单CSV：{path}（可直接发项目部，带回填跟踪列）")

    if stats["有问题记录"] > 0:
        click.echo("\n💡 提示：")
        click.echo("   · 使用 filter 按楼栋/监理员/严重度筛选问题")
        click.echo("   · 使用 list 生成完整整改单（含建议/责任人/CSV导出）")
        click.echo("   · 使用 init-rules 生成项目自定义规则配置")


@main.command("filter")
@common_params
@click.option("--building", "-b", type=str, default=None, help="按楼栋号筛选，如：3号楼")
@click.option("--supervisor", "-u", type=str, default=None, help="按监理员姓名筛选")
@click.option("--severity", type=click.Choice(["critical", "high", "medium", "low"]),
              default=None, help="最低严重程度：critical严重/high重要/medium一般/low轻微")
@click.option("--issue-type", "issue_types", multiple=True,
              type=click.Choice([
                  "missing_position", "missing_strength", "missing_slump",
                  "missing_sample_count", "missing_supervisor_sign",
                  "missing_photo", "photo_time_mismatch", "missing_log",
                  "consistency_building", "consistency_position",
                  "consistency_strength", "consistency_supervisor", "consistency_date"
              ]),
              help="按问题类型筛选（可多次指定）")
@click.option("--consistency-only", is_flag=True, default=False, help="只看资料一致性冲突的记录")
@click.option("--keyword", "-k", type=str, default=None, help="关键词模糊搜索")
@click.option("--show-valid", is_flag=True, default=False, help="同时显示合格记录")
def cmd_filter(project_dir, start_date, end_date, output_dir, verbose, rules_path,
               building, supervisor, severity, issue_types, consistency_only, keyword, show_valid):
    """问题筛选：按楼栋/监理员/严重程度/问题类型精确查找"""
    records, rules = load_and_validate(project_dir, start_date, end_date, verbose, rules_path)
    reporter = ReportGenerator(output_dir, rules=rules)

    sev_map = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }
    itype_map = {
        "missing_position": IssueType.MISSING_POSITION,
        "missing_strength": IssueType.MISSING_STRENGTH,
        "missing_slump": IssueType.MISSING_SLUMP,
        "missing_sample_count": IssueType.MISSING_SAMPLE_COUNT,
        "missing_supervisor_sign": IssueType.MISSING_SUPERVISOR_SIGN,
        "missing_photo": IssueType.MISSING_PHOTO,
        "photo_time_mismatch": IssueType.PHOTO_TIME_MISMATCH,
        "missing_log": IssueType.MISSING_LOG,
        "consistency_building": IssueType.CONSISTENCY_BUILDING,
        "consistency_position": IssueType.CONSISTENCY_POSITION,
        "consistency_strength": IssueType.CONSISTENCY_STRENGTH,
        "consistency_supervisor": IssueType.CONSISTENCY_SUPERVISOR,
        "consistency_date": IssueType.CONSISTENCY_DATE,
    }

    min_severity = sev_map.get(severity) if severity else None
    selected_itypes = [itype_map[t] for t in issue_types] if issue_types else None
    date_range = parse_date_range(start_date, end_date)
    start_dt = date_range[0] if date_range else None
    end_dt = date_range[1] if date_range else None

    filtered = RecordFilter.apply_filters(
        records,
        building=building,
        supervisor=supervisor,
        issue_types=selected_itypes,
        min_severity=min_severity,
        start_date=start_dt,
        end_date=end_dt,
        keyword=keyword,
        issues_only=not show_valid,
    )

    if consistency_only:
        filtered = [r for r in filtered if r.consistency_issues]

    filter_desc_parts = []
    if building: filter_desc_parts.append(f"楼栋={building}")
    if supervisor: filter_desc_parts.append(f"监理={supervisor}")
    if severity: filter_desc_parts.append(f"严重度≥{severity}")
    if selected_itypes: filter_desc_parts.append(f"问题类型={[i.value for i in selected_itypes]}")
    if consistency_only: filter_desc_parts.append("仅一致性冲突")
    if keyword: filter_desc_parts.append(f"关键词={keyword}")
    filter_desc = "  ".join(filter_desc_parts) if filter_desc_parts else "无"

    click.echo("")
    click.echo(f"🔎 筛选条件：{filter_desc}")
    click.echo(f"📊 命中 {len(filtered)} 条记录")
    click.echo("")
    click.echo(reporter.generate_summary_table(filtered, show_all=show_valid))
    click.echo("")
    click.echo("🔗 一致性冲突：")
    click.echo(reporter.generate_consistency_table(filtered))
    click.echo("")
    click.echo("📋 问题明细：")
    click.echo(reporter.generate_issue_detail_table(filtered))

    if filtered:
        path_txt = reporter.save_text_report(filtered)
        click.echo(f"\n💾 已保存筛选结果TXT：{path_txt}")
        path_xlsx = reporter.save_excel_report(filtered)
        if path_xlsx:
            click.echo(f"💾 已保存筛选结果Excel：{path_xlsx}")
        path_csv = reporter.save_action_csv(filtered)
        if path_csv:
            click.echo(f"💾 已保存筛选结果CSV：{path_csv}")


@main.command("list")
@common_params
@click.option("--severity", type=click.Choice(["critical", "high", "medium", "low", "all"]),
              default="all", help="仅显示某严重程度以上（默认全部）")
@click.option("--format", "fmt", type=click.Choice(["text", "excel", "csv", "all"]), default="all",
              help="整改清单输出格式（默认导出全部）")
@click.option("--building", "-b", type=str, default=None, help="仅针对某楼栋生成清单")
@click.option("--consistency-only", is_flag=True, default=False, help="仅导出一致性冲突")
def cmd_list(project_dir, start_date, end_date, output_dir, verbose, rules_path,
             severity, fmt, building, consistency_only):
    """清单生成：按严重程度分级，含整改建议和责任人，可导出CSV发项目部"""
    records, rules = load_and_validate(project_dir, start_date, end_date, verbose, rules_path)
    reporter = ReportGenerator(output_dir, rules=rules)

    if building:
        records = RecordFilter.by_building(records, building)
        click.echo(f"🏢 已按楼栋筛选：{building}，命中 {len(records)} 条记录")

    if severity != "all":
        sev_map = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }
        min_sev = sev_map[severity]
        records = RecordFilter.by_severity(records, min_sev)
        click.echo(f"⚖️  已按严重程度≥{min_sev.value}筛选，命中 {len(records)} 条记录")

    if consistency_only:
        records = [r for r in records if r.consistency_issues]
        click.echo(f"🔗 仅一致性冲突记录：{len(records)} 条")

    click.echo("")
    click.echo(reporter.generate_action_list(records))

    if fmt in ("text", "all"):
        path = reporter.save_action_list(records)
        click.echo(f"\n📄 整改清单TXT：{path}")

    if fmt in ("excel", "all"):
        path = reporter.save_excel_report(records)
        if path:
            click.echo(f"📊 整改清单Excel：{path}（含一致性冲突sheet）")

    if fmt in ("csv", "all"):
        path = reporter.save_action_csv(records)
        if path:
            click.echo(f"📋 整改清单CSV：{path}")
            click.echo("   → 含整改建议、责任岗位；请项目部填写：")
            click.echo("     指定责任人 / 计划完成日期 / 是否整改 / 实际完成日期 / 备注")


@main.command("info")
@common_params
def cmd_info(project_dir, start_date, end_date, output_dir, verbose, rules_path):
    """项目信息概览：楼栋列表、监理员分布、问题类型统计、规则信息"""
    records, rules = load_and_validate(project_dir, start_date, end_date, verbose, rules_path)
    reporter = ReportGenerator(output_dir, rules=rules)

    click.echo("")
    click.echo(reporter.generate_statistics_report(records))

    buildings = RecordFilter.unique_buildings(records)
    supervisors = RecordFilter.unique_supervisors(records)

    click.echo("🏢 楼栋问题分布：")
    if buildings:
        for b in buildings:
            count = sum(1 for r in records if r.building == b)
            issues_count = sum(1 for r in records if r.building == b and r.has_issues)
            consistency_count = sum(1 for r in records if r.building == b and r.consistency_issues)
            rate = f"{(count-issues_count)/count*100:.0f}%" if count else "0%"
            extra = ""
            if consistency_count:
                extra = f"  一致性冲突{consistency_count}条"
            click.echo(f"  - {b:<10} 共{count:>3}条 | 问题{issues_count:>3}条 | 合格{rate}{extra}")
    else:
        click.echo("  （未识别到楼栋信息）")

    click.echo("")
    click.echo("👤 监理员问题分布：")
    if supervisors:
        for s in supervisors:
            count = sum(1 for r in records if r.supervisor == s)
            issues_count = sum(1 for r in records if r.supervisor == s and r.has_issues)
            sign_missing = sum(
                1 for r in records
                if r.supervisor == s and any(i.issue_type == IssueType.MISSING_SUPERVISOR_SIGN for i in r.issues)
            )
            extra = ""
            if sign_missing:
                extra = f"  缺签名{sign_missing}条"
            click.echo(f"  - {s:<10} 共{count:>3}条 | 问题{issues_count:>3}条{extra}")
    else:
        click.echo("  （未识别到监理员信息）")

    click.echo("")
    click.echo("🔗 资料一致性问题汇总：")
    consistency_issues = [r for r in records if r.consistency_issues]
    if consistency_issues:
        for r in consistency_issues:
            for ci in r.consistency_issues:
                click.echo(f"  - {r.record_id[:40]:<42} {ci.description}")
    else:
        click.echo("  ✅ 暂无一致性冲突")

    click.echo("")
    click.echo("⚙️  当前生效规则：")
    if rules.source_file:
        click.echo(f"  来源文件：{rules.source_file}")
    else:
        click.echo("  来源：内置默认规则（建议执行 init-rules 生成项目规则）")
    click.echo(f"  最少照片张数：{rules.min_photo_count}")
    click.echo(f"  照片时间间隔上限：{rules.max_photo_gap_hours} 小时")
    click.echo(f"  照片允许提前：{rules.photo_early_days} 天，滞后：{rules.photo_late_days} 天")
    click.echo(f"  资料一致性核对：{'启用' if rules.consistency_check else '关闭'}")
    click.echo(f"  强制监理签名：{'是' if rules.require_supervisor_sign else '否'}")
    req_info = []
    for fname, cfg in rules.required_fields.items():
        if cfg.get("required", True):
            req_info.append(f"{cfg.get('label', fname)}({cfg['severity'].value})")
    click.echo(f"  必填字段：{', '.join(req_info)}")


@main.command(name="weekly", help="生成每周抽查汇总报告（按楼栋、监理员、问题类型统计）")
@click.option("--project", "-p", required=True, type=click.Path(exists=True), help="项目根目录")
@click.option("--start-date", "-s", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", "-e", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--output", "-o", default=".", help="报告输出目录")
@click.option("--format", "-f", "fmt", default="table",
              type=click.Choice(["table", "csv", "excel", "all"]), help="输出格式")
@click.option("--rules", "-r", default=None, type=click.Path(), help="规则配置文件路径")
def weekly_report(project, start_date, end_date, output, fmt, rules):
    project_path = Path(project).resolve()
    out_dir = Path(output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records, rules_obj = load_and_validate(project_path, start_date, end_date, verbose=False, rules_path=rules)
    if not records:
        click.echo("⚠️  日期范围内没有找到浇筑记录")
        return

    reporter = ReportGenerator(out_dir, rules_obj)
    click.echo(reporter.generate_weekly_summary(records))
    click.echo("")

    if fmt in ("csv", "all"):
        csv_path = reporter.save_weekly_csv(records)
        if csv_path:
            click.echo(f"📄 周报CSV已导出：{csv_path}")
    if fmt in ("excel", "all"):
        xlsx_path = reporter.save_weekly_excel(records)
        if xlsx_path:
            click.echo(f"📊 周报Excel已导出：{xlsx_path}")


@main.command(name="track", help="导入历史整改CSV，跟踪问题整改进展")
@click.option("--project", "-p", required=True, type=click.Path(exists=True), help="项目根目录")
@click.option("--historical", "-i", required=True, type=click.Path(exists=True), help="上周导出的整改CSV文件路径")
@click.option("--start-date", "-s", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", "-e", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--output", "-o", default=".", help="报告输出目录")
@click.option("--format", "-f", "fmt", default="table",
              type=click.Choice(["table", "csv", "all"]), help="输出格式")
@click.option("--rules", "-r", default=None, type=click.Path(), help="规则配置文件路径")
def track_report(project, historical, start_date, end_date, output, fmt, rules):
    project_path = Path(project).resolve()
    out_dir = Path(output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    hist_path = Path(historical).resolve()

    records, rules_obj = load_and_validate(project_path, start_date, end_date, verbose=False, rules_path=rules)

    from .tracker import IssueTracker
    tracker = IssueTracker(str(hist_path))
    click.echo(f"📋 已加载历史整改记录：{len(tracker.historical_issues)} 条（来自 {hist_path.name}）")
    click.echo("")

    result = tracker.compare_with_current(records)
    click.echo(tracker.generate_tracking_report(result, project_path.name))

    if fmt in ("csv", "all"):
        csv_path = tracker.save_tracking_csv(result, str(out_dir))
        if csv_path:
            click.echo(f"")
            click.echo(f"📄 跟踪报告CSV已导出：{csv_path}")


if __name__ == "__main__":
    main()
