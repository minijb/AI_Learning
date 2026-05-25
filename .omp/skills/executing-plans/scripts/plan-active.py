#!/usr/bin/env python3
"""
plan-active.py — 展示所有活跃计划（Rich Panel 卡片格式）
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, get_progress_summary, get_console, \
    read_file_safe, extract_goal, extract_task_titles, \
    extract_blocked_lines, parse_task_checkboxes, render_progress_bar
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box


def _status_style(status: str) -> str:
    """Map status string to Rich style."""
    return {
        "BLOCKED": "plan.status.blocked",
        "DONE": "plan.status.done",
        "IN_PROGRESS": "plan.status.progress",
        "PENDING": "plan.status.pending",
    }.get(status, "muted")


def main():
    env = get_env()
    console = get_console()
    active_dir = env.active_dir

    if not active_dir.exists() or not active_dir.is_dir():
        console.print("[warn]没有活跃计划。[/warn]")
        sys.exit(0)

    items = [p for p in active_dir.iterdir() if p.name != ".gitkeep"]
    items = [p for p in items if not p.is_dir() or
             any((p / f).exists() for f in ["exec-plan.md", "feature-list.json", "progress.txt"])]
    if not items:
        console.print("[warn]没有活跃计划。[/warn]")
        sys.exit(0)

    total_done = 0
    total_all = 0
    total_blocked = 0

    for item in sorted(items):
        plan_name = item.stem if item.is_file() else item.name
        is_dir = item.is_dir()
        type_label = "FULL" if is_dir else "QUICK"

        # ── exec-plan.md extraction ──
        goal_text = ""
        exec_tasks: list[str] = []
        if is_dir:
            exec_plan_path = item / "exec-plan.md"
            ep_content = read_file_safe(exec_plan_path)
            if ep_content is None:
                goal_text = "（无 exec-plan.md）" if not exec_plan_path.exists() else "（编码错误）"
            else:
                goal_text = extract_goal(ep_content)
                exec_tasks = extract_task_titles(ep_content)
        else:
            content = read_file_safe(item)
            if content is None:
                goal_text = "（编码错误）"
            else:
                goal_text = extract_goal(content)
                exec_tasks = extract_task_titles(content)

        # ── Progress summary ──
        summary = get_progress_summary(item)
        feat_total = summary["total"]
        feat_done = summary["done"]
        blocked_count = summary["blocked"]

        total_done += feat_done
        total_all += feat_total
        total_blocked += blocked_count

        # ── Status ──
        if blocked_count > 0:
            status = "BLOCKED"
        elif feat_total > 0 and feat_done >= feat_total:
            status = "DONE"
        elif feat_done > 0:
            status = "IN_PROGRESS"
        else:
            status = "PENDING"

        pct = (feat_done * 100 // feat_total) if feat_total > 0 else None

        # ── Build Panel content as Text ──
        content_lines: list[Text] = []

        # Goal line
        content_lines.append(Text("目标: ", style="muted") + Text(goal_text[:100]))

        # Progress bar
        bar = render_progress_bar(feat_done, feat_total)
        pct_display = f"{pct}%" if pct is not None else "--%"
        progress_line = Text.from_markup(f"进度: {bar}  ")
        progress_line.append(f"{feat_done}/{feat_total} ({pct_display})", style="highlight")
        content_lines.append(progress_line)

        # Tasks line
        task_parts: list[str] = []
        has_tasks_dir = is_dir and (item / "tasks").is_dir()
        if has_tasks_dir:
            tasks_dir = item / "tasks"
            task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == ".md"])
            for tf in task_files:
                tc = read_file_safe(tf)
                if tc:
                    all_cb = len(re.findall(r'- \[.\]', tc))
                    done_cb = len(re.findall(r'- \[x\]', tc))
                    flag = all_cb > 0 and done_cb >= all_cb
                else:
                    flag = False
                icon = "[success]✓[/success]" if flag else "[muted]✗[/muted]"
                task_parts.append(f"{icon} {tf.stem}")
        elif exec_tasks:
            progress_path = item / "progress.txt" if is_dir else None
            if is_dir and progress_path and progress_path.exists():
                pc = read_file_safe(progress_path) or ""
                task_status = parse_task_checkboxes(pc)
                for label in exec_tasks:
                    # Match by prefix (Task N)
                    task_prefix = label.split(" — ")[0] if " — " in label else label
                    done_flag = False
                    for pl, is_done in task_status.items():
                        if pl.startswith(task_prefix):
                            done_flag = is_done
                            break
                    icon = "[success]✓[/success]" if done_flag else "[muted]✗[/muted]"
                    task_parts.append(f"{icon} {label}")
            else:
                for label in exec_tasks:
                    task_parts.append(f"[muted]?[/muted] {label}")

        if task_parts:
            content_lines.append(Text("任务:", style="muted"))
            for part in task_parts:
                content_lines.append(Text.from_markup(f"  {part}"))

        # Blocked info
        if is_dir:
            progress_path = item / "progress.txt"
            if progress_path.exists():
                pc = read_file_safe(progress_path)
                blocked_info = "无"
                if pc:
                    blocked = extract_blocked_lines(pc)
                    if blocked:
                        first = blocked[0]
                        blocked_info = first[:80] + "..." if len(first) > 80 else first
                content_lines.append(Text("阻塞: ", style="muted") +
                                     Text(blocked_info, style="plan.status.blocked" if blocked_info != "无" else "muted"))

        # Assemble Text renderable
        body = Text()
        for i, line in enumerate(content_lines):
            if i > 0:
                body.append("\n")
            body.append(line)

        # ── Render Panel ──
        title_parts = Text()
        title_parts.append(plan_name, style="plan.name")
        title_parts.append("  ")
        title_parts.append(f"[{type_label}]", style="plan.type")
        title_parts.append("  ")
        title_parts.append(status, style=_status_style(status))

        panel = Panel(
            body,
            title=title_parts,
            title_align="left",
            border_style=_status_style(status),
            box=box.ROUNDED,
            padding=(0, 1),
        )
        console.print(panel)
        console.print()

    # ── Summary ──
    overall_pct = (total_done * 100 // total_all) if total_all > 0 else 0
    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_column(style="highlight", justify="right")
    summary_table.add_column()
    summary_table.add_row("总进度:", f"{total_done}/{total_all} ({overall_pct}%)")
    summary_table.add_row("阻塞:", str(total_blocked))
    summary_table.add_row("活跃计划:", str(len(items)))
    console.print(Panel(summary_table, title="汇总", title_align="left", border_style="muted"))


if __name__ == "__main__":
    main()
