#!/usr/bin/env python3
"""
plan-status.py — 查看所有活跃计划的进度
使用 Rich Table 输出结构化表格。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, get_progress_summary, get_console, \
    render_progress_bar, read_file_safe
from rich.table import Table


def main():
    env = get_env()
    console = get_console()
    active_dir = env.active_dir

    if not active_dir.exists():
        console.print("[warn]没有活跃计划。[/warn] (docs/exec-plans/active/ 目录不存在)")
        console.print("[muted]创建计划:[/muted] plan-new.py --full '计划名称'")
        return

    items = [p for p in active_dir.iterdir() if p.name != ".gitkeep"]

    if not items:
        console.print("[warn]没有活跃计划。[/warn]")
        console.print("[muted]创建计划:[/muted] plan-new.py --full '计划名称'")
        return

    table = Table(title="活跃计划", title_style="bold", box=None, padding=(0, 2))
    table.add_column("计划", style="plan.name", min_width=24)
    table.add_column("类型", style="plan.type", width=6)
    table.add_column("状态", width=16)
    table.add_column("进度", justify="right", width=10)
    table.add_column("进度条", width=14)
    table.add_column("Tasks", width=8)

    total_done = 0
    total_all = 0
    total_blocked = 0

    for item in sorted(items):
        plan_name = item.stem if item.is_file() else item.name

        if item.is_dir():
            has_exec = (item / "exec-plan.md").exists()
            has_features = (item / "feature-list.json").exists()
            if not has_exec and not has_features:
                continue
            type_mark = "[plan.type]FULL[/plan.type]"
            summary = get_progress_summary(item)
            done_count = summary["done"]
            feat_count = summary["total"]
            blocked = summary["blocked"]

            total_done += done_count
            total_all += feat_count
            total_blocked += blocked

            pct = (done_count * 100 // feat_count) if feat_count else 0

            if blocked > 0:
                status = f"[plan.status.blocked]BLOCKED:{blocked}[/plan.status.blocked]"
            elif done_count >= feat_count and feat_count > 0:
                status = "[plan.status.done]DONE[/plan.status.done]"
            else:
                status = "[plan.status.progress]IN_PROGRESS[/plan.status.progress]"

            progress_text = f"{done_count}/{feat_count} ({pct}%)"
            bar = render_progress_bar(done_count, feat_count)

            # Task stats from tasks/ directory
            tasks_dir = item / "tasks"
            task_display = ""
            if tasks_dir.is_dir():
                task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == '.md'])
                if task_files:
                    task_total = len(task_files)
                    task_done = 0
                    for tf in task_files:
                        tc = read_file_safe(tf)
                        if tc:
                            all_cb = len(re.findall(r'- \[.\]', tc))
                            done_cb = len(re.findall(r'- \[x\]', tc))
                            if all_cb > 0 and done_cb >= all_cb:
                                task_done += 1
                    task_display = f"{task_done}/{task_total}"

            table.add_row(plan_name, type_mark, status, progress_text, bar, task_display)

        else:
            type_mark = "[plan.type]QUICK[/plan.type]"
            content = read_file_safe(item)
            if content is None:
                table.add_row(plan_name, type_mark, "[muted]编码错误[/muted]", "—", "—", "—")
                continue

            step_total = len(re.findall(r"- \[.\] \*\*Step", content))
            step_done = len(re.findall(r"- \[x\] \*\*Step", content))

            pct = (step_done * 100 // step_total) if step_total else 0
            total_done += step_done
            total_all += step_total

            if "[BLOCKED]" in content:
                status = "[plan.status.blocked]BLOCKED[/plan.status.blocked]"
            elif step_done >= step_total and step_total > 0:
                status = "[plan.status.done]DONE[/plan.status.done]"
            else:
                status = "[plan.status.progress]IN_PROGRESS[/plan.status.progress]"

            progress_text = f"{step_done}/{step_total} ({pct}%)"
            bar = render_progress_bar(step_done, step_total)

            table.add_row(plan_name, type_mark, status, progress_text, bar, "—")

    console.print(table)

    # Summary
    console.print()
    overall_pct = (total_done * 100 // total_all) if total_all > 0 else 0
    summary_text = (
        f"[highlight]总进度:[/highlight] {total_done}/{total_all} ({overall_pct}%)  "
        f"[highlight]阻塞:[/highlight] {total_blocked}  "
        f"[highlight]活跃计划:[/highlight] {len(items)}"
    )
    console.print(f"  {summary_text}")


if __name__ == "__main__":
    main()
