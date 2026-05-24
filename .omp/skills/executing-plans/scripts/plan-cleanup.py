#!/usr/bin/env python3
"""
plan-cleanup.py — 清理计划文件（跨平台 Python）
用法: python plan-cleanup.py --all --what-if
"""

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows terminal UTF-8 support
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from common import error, error_exit, get_env, info, read_plan_json, warn


def cleanup_completed(completed_dir: Path, days: int, what_if: bool, force: bool) -> int:
    deleted = 0
    found = False
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400

    for item in completed_dir.iterdir():
        if item.name == ".gitkeep":
            continue
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            found = True
            age_days = int((datetime.now(timezone.utc).timestamp() - mtime) / 86400)
            prefix = "[WHATIF] " if what_if else ""
            print(f"{prefix}{item.name:<50} {age_days}天前")
            if not what_if:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1

    if not found:
        info(f"completed/ 中没有超过 {days} 天的文件。")
    return deleted


def cleanup_orphaned(completed_dir: Path, what_if: bool) -> int:
    deleted = 0
    found = False
    if not completed_dir.exists():
        info("没有 summary 文件需要清理。")
        return deleted

    summaries = [p for p in completed_dir.iterdir() if p.name.endswith("-summary.txt")]
    if not summaries:
        info("没有 summary 文件需要清理。")
        return deleted

    for s in summaries:
        base = s.stem.replace("-summary", "")
        has_plan = (completed_dir / f"{base}.md").exists() or (completed_dir / base).is_dir()
        if not has_plan:
            found = True
            prefix = "[WHATIF] " if what_if else ""
            print(f"{prefix}{s.name}")
            if not what_if:
                s.unlink()
                deleted += 1

    if not found:
        info("没有孤立的 summary 文件。")
    return deleted


def cleanup_empty(active_dir: Path, what_if: bool) -> int:
    deleted = 0
    found = False
    if not active_dir.exists():
        info("active/ 中没有未开始的计划。")
        return deleted

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
            found = True
            prefix = "[WHATIF] " if what_if else ""
            print(f"{prefix}{item.name}")
            if not what_if:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1

    if not found:
        info("active/ 中没有未开始的计划。")
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

    flag_completed = args.completed or args.all
    flag_orphaned = args.orphaned or args.all
    flag_empty = args.empty or args.all

    if not (flag_completed or flag_orphaned or flag_empty):
        error_exit(
            "缺少选项: 至少指定一个操作: --completed, --orphaned, --empty, --all",
            "查看帮助: python plan-cleanup.py --help"
        )

    if not args.force and not args.what_if:
        print("即将执行以下清理操作:")
        if flag_completed:
            print(f"  - 清理 {args.days}天前的归档")
        if flag_orphaned:
            print("  - 清理孤立 summary")
        if flag_empty:
            print("  - 清理未开始的活跃计划")
        confirm = input("继续? (y/N): ").strip().lower()
        if confirm != "y":
            print("已取消。")
            return

    deleted_total = 0
    if flag_completed:
        print()
        print(f"===== 旧归档清理（>{args.days}天） =====")
        deleted_total += cleanup_completed(env.completed_dir, args.days, args.what_if, args.force)

    if flag_orphaned:
        print()
        print("===== 孤立 Summary 清理 =====")
        deleted_total += cleanup_orphaned(env.completed_dir, args.what_if)

    if flag_empty:
        print()
        print("===== 空计划清理（未开始 / 0%） =====")
        deleted_total += cleanup_empty(env.active_dir, args.what_if)

    print()
    if args.what_if:
        info("本次为预览模式，未执行任何删除。")
    else:
        info(f"清理完成。删除了 {deleted_total} 个项目。")


if __name__ == "__main__":
    main()
