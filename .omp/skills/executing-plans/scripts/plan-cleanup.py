#!/usr/bin/env python3
"""
plan-cleanup.py — 清理计划文件
用法: python plan-cleanup.py --all --what-if
"""

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import error, error_exit, get_env, info, read_plan_json, warn, get_console
from rich.table import Table
from rich import box


def cleanup_completed(completed_dir: Path, days: int, what_if: bool, force: bool) -> int:
    console = get_console()
    deleted = 0
    found_any = False
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400

    table = Table(title=f"旧归档清理（>{days}天）", box=box.SIMPLE, padding=(0, 1))
    table.add_column("计划", style="plan.name")
    table.add_column("天数前", justify="right")
    table.add_column("操作", style="muted")

    for item in completed_dir.iterdir():
        if item.name == ".gitkeep":
            continue
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            found_any = True
            age_days = int((datetime.now(timezone.utc).timestamp() - mtime) / 86400)
            action = "[muted]预览[/muted]" if what_if else "[error]删除[/error]"
            table.add_row(item.name, str(age_days), action)
            if not what_if:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1

    if found_any:
        console.print(table)
    else:
        console.print(f"[info]▸[/info] completed/ 中没有超过 {days} 天的文件。")
    return deleted


def cleanup_orphaned(completed_dir: Path, what_if: bool) -> int:
    console = get_console()
    deleted = 0
    if not completed_dir.exists():
        console.print("[info]▸[/info] 没有 summary 文件需要清理。")
        return deleted

    summaries = [p for p in completed_dir.iterdir() if p.name.endswith("-summary.txt")]
    if not summaries:
        console.print("[info]▸[/info] 没有 summary 文件需要清理。")
        return deleted

    found_any = False
    table = Table(title="孤立 Summary 清理", box=box.SIMPLE, padding=(0, 1))
    table.add_column("文件")
    table.add_column("操作", style="muted")

    for s in summaries:
        base = s.stem.replace("-summary", "")
        has_plan = (completed_dir / f"{base}.md").exists() or (completed_dir / base).is_dir()
        if not has_plan:
            found_any = True
            action = "[muted]预览[/muted]" if what_if else "[error]删除[/error]"
            table.add_row(s.name, action)
            if not what_if:
                s.unlink()
                deleted += 1

    if found_any:
        console.print(table)
    else:
        console.print("[info]▸[/info] 没有孤立的 summary 文件。")
    return deleted


def cleanup_empty(active_dir: Path, what_if: bool) -> int:
    console = get_console()
    deleted = 0
    if not active_dir.exists():
        console.print("[info]▸[/info] active/ 中没有未开始的计划。")
        return deleted

    found_any = False
    table = Table(title="空计划清理（未开始 / 0%）", box=box.SIMPLE, padding=(0, 1))
    table.add_column("计划", style="plan.name")
    table.add_column("操作", style="muted")

    for item in active_dir.iterdir():
        if item.name == ".gitkeep":
            continue

        is_empty = False
        if item.is_dir():
            feature_file = item / "feature-list.json"
            progress_file = item / "progress.txt"
            feat_count = 0
            done_count = 0

            if feature_file.exists():
                data = read_plan_json(feature_file)
                if data:
                    features = data.get("features", [])
                    feat_count = len(features)
                    done_count = sum(1 for f in features if f.get("passes") is True)

            if feat_count == 0:
                is_empty = True

            if is_empty and progress_file.exists():
                content = progress_file.read_text(encoding="utf-8")
                if re.search(r"状态:\s*(IN_PROGRESS|BLOCKED|COMPLETED)", content):
                    is_empty = False
        else:
            content = item.read_text(encoding="utf-8")
            step_total = len(re.findall(r"- \[.\] \*\*Step", content))
            if step_total == 0:
                is_empty = True

        if is_empty:
            found_any = True
            action = "[muted]预览[/muted]" if what_if else "[error]删除[/error]"
            table.add_row(item.name, action)
            if not what_if:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1

    if found_any:
        console.print(table)
    else:
        console.print("[info]▸[/info] active/ 中没有未开始的计划。")
    return deleted


def main():
    parser = argparse.ArgumentParser(description="清理计划文件")
    parser.add_argument("--completed", action="store_true", help="清理 completed 目录中超过 --days 天的已归档计划")
    parser.add_argument("--orphaned", action="store_true", help="清理 completed 目录中没有对应计划的 summary 文件")
    parser.add_argument("--empty", action="store_true", help="清理 active 目录中未开始（0% 进度）的计划")
    parser.add_argument("--all", action="store_true", help="执行全部清理操作")
    parser.add_argument("--days", type=int, default=30, help="定义'旧'的天数阈值（默认 30）")
    parser.add_argument("--what-if", "-n", action="store_true", help="仅预览，不实际删除")
    parser.add_argument("--force", action="store_true", help="跳过确认，直接执行")
    args = parser.parse_args()

    env = get_env()
    console = get_console()

    flag_completed = args.completed or args.all
    flag_orphaned = args.orphaned or args.all
    flag_empty = args.empty or args.all

    if not (flag_completed or flag_orphaned or flag_empty):
        error_exit(
            "缺少选项: 至少指定一个操作: --completed, --orphaned, --empty, --all",
            "查看帮助: python plan-cleanup.py --help"
        )

    if not args.force and not args.what_if:
        ops = []
        if flag_completed:
            ops.append(f"清理 {args.days}天前的归档")
        if flag_orphaned:
            ops.append("清理孤立 summary")
        if flag_empty:
            ops.append("清理未开始的活跃计划")
        console.print("[warn]即将执行以下清理操作:[/warn]")
        for op in ops:
            console.print(f"  - {op}")
        confirm = input("继续? (y/N): ").strip().lower()
        if confirm != "y":
            console.print("已取消。")
            return

    deleted_total = 0
    if flag_completed:
        console.print()
        deleted_total += cleanup_completed(env.completed_dir, args.days, args.what_if, args.force)

    if flag_orphaned:
        console.print()
        deleted_total += cleanup_orphaned(env.completed_dir, args.what_if)

    if flag_empty:
        console.print()
        deleted_total += cleanup_empty(env.active_dir, args.what_if)

    console.print()
    if args.what_if:
        info("本次为预览模式，未执行任何删除。")
    else:
        console.print(f"[success]✓[/success] 清理完成。删除了 {deleted_total} 个项目。")


if __name__ == "__main__":
    main()
