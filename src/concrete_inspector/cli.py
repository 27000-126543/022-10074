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


def _fix_console_encoding():
    """解决Windows控制台GBK编码无法显示emoji的问题"""
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


def common_params(func):
    decorators = [
        click.option("--project-dir", "-p", type=click.Path(exists=True, file_okay=False, path_type=str),
                     required=True, help="项目根目录（包含各浇筑记录子文件夹）"),
        click.option("--start-date", "-s", type=str, default=None,
                     help="检查范围起始日期，格式：2024-01-01 或 20240101"),
        click.option("--end-date", "-e", type=str, default=None,
                     help="检查范围结束日期，格式：2024-01-31 或 20240131"),
        click.option("--output-dir", "-o", type=click.Path(file_okay=False, path_type=str),
                     default=None, help="报告输出目录（默认为当前目录）"),
        click.option("--verbose", "-v", is_flag=True, default=False, help="显示详细日志"),
    ]
    for d in reversed(decorators):
        func = d(func)
    return func


def load_and_validate(project_dir: str, start_date: Optional[str], end_date: Optional[str], verbose: bool):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    click.echo(f"📂 正在扫描项目目录：{project_dir}")
    date_range = parse_date_range(start_date, end_date)
    if date_range:
        s, e = date_range
        click.echo(f"📅 检查日期范围：{s.strftime('%Y-%m-%d')} ~ {e.strftime('%Y-%m-%d')}")

    scanner = DirectoryScanner(project_dir, date_range=date_range)
    records = scanner.scan()
    click.echo(f"✅ 扫描完成，共发现 {len(records)} 条浇筑记录")

    validator = RecordValidator()
    validator.validate_all(records)

    with_issues = [r for r in records if r.has_issues]
    click.echo(f"🔍 校验完成，其中 {len(with_issues)} 条记录存在问题")
    return records


@click.group()
@click.version_option(version=__version__, prog_name="concrete-inspector")
@click.help_option("-h", "--help")
def main():
    """混凝土浇筑旁站批量检查工具

    面向总包质量部门或监理公司内业人员，每周抽查项目旁站资料。

    核心命令：
      check   批量核对（默认功能）
      filter  问题筛选（按楼栋/监理员/异常类型）
      list    清单生成（按严重程度生成整改单）

    示例：
      concrete-inspector check -p ./某项目 -s 2024-01-01 -e 2024-01-31
      concrete-inspector filter -p ./某项目 --building 3号楼 --supervisor 张三
      concrete-inspector list -p ./某项目 --severity high -o ./reports
    """
    pass


@main.command("check")
@common_params
@click.option("--show-all", is_flag=True, default=False, help="显示全部记录（包括合格的）")
@click.option("--format", "fmt", type=click.Choice(["table", "txt", "excel", "all"]), default="table",
              help="输出格式：table(控制台表格)/txt/excel/all")
def cmd_check(project_dir, start_date, end_date, output_dir, verbose, show_all, fmt):
    """批量核对：检查每条记录的必填字段和旁站资料完整性"""
    records = load_and_validate(project_dir, start_date, end_date, verbose)
    reporter = ReportGenerator(output_dir)

    stats = get_statistics(records)
    click.echo("")
    click.echo(reporter.generate_statistics_report(records))

    if fmt in ("table", "all"):
        click.echo("")
        click.echo("📌 检查结果概览：")
        click.echo(reporter.generate_summary_table(records, show_all=show_all))

    if fmt in ("txt", "all"):
        path = reporter.save_text_report(records)
        click.echo(f"\n💾 已生成TXT报告：{path}")

    if fmt in ("excel", "all"):
        path = reporter.save_excel_report(records)
        if path:
            click.echo(f"💾 已生成Excel报告：{path}")

    if stats["有问题记录"] > 0:
        click.echo("\n💡 提示：使用 'filter' 命令可按条件筛选问题，使用 'list' 命令生成整改清单")


@main.command("filter")
@common_params
@click.option("--building", "-b", type=str, default=None, help="按楼栋号筛选，如：3号楼")
@click.option("--supervisor", "-u", type=str, default=None, help="按监理员姓名筛选")
@click.option("--severity", type=click.Choice(["critical", "high", "medium", "low"]),
              default=None, help="最低严重程度：critical(严重)/high(重要)/medium(一般)/low(轻微)")
@click.option("--issue-type", "issue_types", multiple=True,
              type=click.Choice([
                  "missing_position", "missing_strength", "missing_slump",
                  "missing_sample_count", "missing_supervisor_sign",
                  "missing_photo", "photo_time_mismatch", "missing_log"
              ]),
              help="按问题类型筛选（可多次指定）")
@click.option("--keyword", "-k", type=str, default=None, help="关键词模糊搜索（部位/楼栋/问题描述）")
@click.option("--show-valid", is_flag=True, default=False, help="同时显示合格记录")
def cmd_filter(project_dir, start_date, end_date, output_dir, verbose,
               building, supervisor, severity, issue_types, keyword, show_valid):
    """问题筛选：按楼栋、监理员、严重程度或问题类型精确查看"""
    records = load_and_validate(project_dir, start_date, end_date, verbose)
    reporter = ReportGenerator(output_dir)

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

    filter_desc_parts = []
    if building: filter_desc_parts.append(f"楼栋={building}")
    if supervisor: filter_desc_parts.append(f"监理={supervisor}")
    if severity: filter_desc_parts.append(f"严重度≥{severity}")
    if selected_itypes: filter_desc_parts.append(f"问题类型={[i.value for i in selected_itypes]}")
    if keyword: filter_desc_parts.append(f"关键词={keyword}")
    filter_desc = "  ".join(filter_desc_parts) if filter_desc_parts else "无"

    click.echo("")
    click.echo(f"🔎 筛选条件：{filter_desc}")
    click.echo(f"📊 命中 {len(filtered)} 条记录")
    click.echo("")
    click.echo(reporter.generate_summary_table(filtered, show_all=show_valid))
    click.echo("")
    click.echo("📋 问题明细：")
    click.echo(reporter.generate_issue_detail_table(filtered))

    if filtered:
        path_txt = reporter.save_text_report(filtered)
        click.echo(f"\n💾 已保存筛选结果TXT：{path_txt}")
        path_xlsx = reporter.save_excel_report(filtered)
        if path_xlsx:
            click.echo(f"💾 已保存筛选结果Excel：{path_xlsx}")


@main.command("list")
@common_params
@click.option("--severity", type=click.Choice(["critical", "high", "medium", "low", "all"]),
              default="all", help="仅显示某严重程度以上（默认全部列出）")
@click.option("--format", "fmt", type=click.Choice(["text", "excel", "all"]), default="text",
              help="整改清单输出格式")
@click.option("--building", "-b", type=str, default=None, help="仅针对某楼栋生成清单")
def cmd_list(project_dir, start_date, end_date, output_dir, verbose, severity, fmt, building):
    """清单生成：按严重程度列出待补资料，可直接发项目部整改"""
    records = load_and_validate(project_dir, start_date, end_date, verbose)
    reporter = ReportGenerator(output_dir)

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

    click.echo("")
    click.echo(reporter.generate_action_list(records))

    if fmt in ("text", "all"):
        path = reporter.save_action_list(records)
        click.echo(f"\n📄 整改清单已保存：{path}")

    if fmt in ("excel", "all"):
        path = reporter.save_excel_report(records)
        if path:
            click.echo(f"📊 Excel版报告已保存：{path}")


@main.command("info")
@common_params
def cmd_info(project_dir, start_date, end_date, output_dir, verbose):
    """查看项目目录的基础信息（楼栋列表、监理员列表等）"""
    records = load_and_validate(project_dir, start_date, end_date, verbose)

    buildings = RecordFilter.unique_buildings(records)
    supervisors = RecordFilter.unique_supervisors(records)

    click.echo("")
    click.echo("🏢 涉及楼栋列表：")
    if buildings:
        for b in buildings:
            count = sum(1 for r in records if r.building == b)
            issues_count = sum(1 for r in records if r.building == b and r.has_issues)
            click.echo(f"  - {b:<10} 共{count:>3}条记录，其中{issues_count:>3}条有问题")
    else:
        click.echo("  （未识别到楼栋信息，建议在文件夹名或清单中注明楼栋号）")

    click.echo("")
    click.echo("👤 涉及监理员列表：")
    if supervisors:
        for s in supervisors:
            count = sum(1 for r in records if r.supervisor == s)
            issues_count = sum(1 for r in records if r.supervisor == s and r.has_issues)
            click.echo(f"  - {s:<10} 共{count:>3}条记录，其中{issues_count:>3}条有问题")
    else:
        click.echo("  （未识别到监理员信息，建议在清单中填写）")

    stats = get_statistics(records)
    click.echo("")
    click.echo("📈 问题类型统计：")
    for issue_name, count in sorted(stats["问题类型分布"].items(), key=lambda x: -x[1]):
        click.echo(f"  - {issue_name:<12} {count:>4} 项")


if __name__ == "__main__":
    main()
