#!/usr/bin/env python3
"""
plan-search.py — 搜索 PLAN.md 和 PLAN_COMPLETED.md
用法: python plan-search.py <关键词>
       python plan-search.py --all
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, init_index_files, search_plan_index, warn, get_console
from rich.table import Table
from rich.panel import Panel


def main():
    parser = argparse.ArgumentParser(description="搜索计划索引（PLAN.md + PLAN_COMPLETED.md）")
    parser.add_argument("keyword", nargs="?", default="", help="搜索关键词")
    parser.add_argument("--all", action="store_true", help="列出所有条目")
    args = parser.parse_args()

    console = get_console()
    init_index_files()

    if args.all:
        keyword = ""
        console.print("[heading]所有计划条目[/heading]")
    elif args.keyword:
        keyword = args.keyword
        console.print(f"[heading]搜索: \"{keyword}\"[/heading]")
    else:
        parser.print_help()
        return

    results = search_plan_index(keyword if keyword else "")

    if not results:
        console.print()
        if keyword:
            console.print(f"[warn]未找到匹配 \"{keyword}\" 的计划。[/warn]")
        else:
            console.print("[muted]索引中暂无计划条目。[/muted]")
        return

    # Group by source
    plan_entries = [r for r in results if r["source"] == "PLAN.md"]
    completed_entries = [r for r in results if r["source"] == "PLAN_COMPLETED.md"]

    if plan_entries:
        console.print()
        table = Table(title="PLAN.md（活跃计划）", title_style="bold", box=None, padding=(0, 1))
        table.add_column("类型", style="plan.type", width=8)
        table.add_column("状态", width=10)
        table.add_column("计划", style="plan.name")
        table.add_column("摘要")

        for r in plan_entries:
            extra = r.get("extra", "")
            status_style = {
                "TODO": "plan.status.pending",
                "IN_PROGRESS": "plan.status.progress",
                "DONE": "plan.status.done",
                "BLOCKED": "plan.status.blocked",
            }.get(extra, "muted")
            table.add_row(f"[{r['type']}]", f"[{status_style}]{extra}[/{status_style}]" if extra else "",
                          r["name"], r["summary"])

        console.print(table)

    if completed_entries:
        console.print()
        table = Table(title="PLAN_COMPLETED.md（已完成计划）", title_style="bold", box=None, padding=(0, 1))
        table.add_column("完成日期", style="success", width=12)
        table.add_column("类型", style="plan.type", width=8)
        table.add_column("计划", style="plan.name")
        table.add_column("摘要")

        for r in completed_entries:
            extra = r.get("extra", "")
            table.add_row(extra, f"[{r['type']}]", r["name"], r["summary"])

        console.print(table)

    console.print()
    console.print(f"[highlight]共 {len(results)} 条匹配[/highlight]")

    if keyword:
        console.print()
        console.print("[muted]💡 提示: 创建新计划前，建议先运行此命令查看是否有类似计划可复用。[/muted]")


if __name__ == "__main__":
    main()
