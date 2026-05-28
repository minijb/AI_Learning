#!/usr/bin/env python3
"""
learn-active.py — 展示所有活跃学习计划（Rich Panel 卡片格式）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    get_env, get_console, read_file_safe,
    parse_plan_md, parse_progress_md,
    extract_title, extract_meta, render_progress_bar,
)
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box


def _status_style(status: str) -> str:
    return {
        "DONE": "learn.status.done",
        "IN_PROGRESS": "learn.status.progress",
        "PENDING": "learn.status.pending",
    }.get(status, "muted")


def main():
    env = get_env()
    console = get_console()
    active_dir = env.active_dir

    if not active_dir.exists() or not active_dir.is_dir():
        console.print("[warn]没有活跃的学习计划。[/warn]")
        sys.exit(0)

    plans = sorted([
        p for p in active_dir.iterdir()
        if p.is_dir() and p.name != ".gitkeep"
    ])
    if not plans:
        console.print("[warn]没有活跃的学习计划。[/warn]")
        sys.exit(0)

    total_topics = 0
    total_done = 0
    total_ms = 0
    total_ms_done = 0

    for plan_dir in plans:
        plan_name = plan_dir.name
        plan_path = plan_dir / "plan.md"
        progress_path = plan_dir / "progress.md"

        # ── Read files ──
        plan_content = read_file_safe(plan_path)
        progress_content = read_file_safe(progress_path)

        if plan_content is None:
            console.print(f"[warn]⚠ {plan_name}: plan.md 不可读[/warn]")
            continue

        # ── Parse plan.md ──
        plan_data = parse_plan_md(plan_content)
        title = extract_title(plan_content)
        created_date = extract_meta(plan_content, "创建日期")
        est_hours = extract_meta(plan_content, "预计总耗时")
        goal_text = plan_data["goal_lines"][0] if plan_data["goal_lines"] else "（无目标摘要）"

        # ── Parse progress.md ──
        if progress_content is not None:
            progress = parse_progress_md(progress_content)
        else:
            progress = {"topic_total": 0, "topic_done": 0,
                        "milestone_total": 0, "milestone_done": 0, "blocked": 0}

        topic_total = progress["topic_total"]
        topic_done = progress["topic_done"]
        ms_total = progress["milestone_total"]
        ms_done = progress["milestone_done"]

        # Fallback: count from plan.md learning path table
        if topic_total == 0:
            topic_total = len(plan_data["topics"])

        total_topics += topic_total
        total_done += topic_done
        total_ms += ms_total
        total_ms_done += ms_done

        # ── Status ──
        if topic_total > 0 and topic_done >= topic_total:
            status = "DONE"
        elif topic_done > 0:
            status = "IN_PROGRESS"
        else:
            status = "PENDING"

        pct = (topic_done * 100 // topic_total) if topic_total > 0 else None

        # ── Build Panel body ──
        body = Text()

        # Title line
        body.append(Text("名称: ", style="muted") + Text(title, style="learn.name"))
        body.append("\n")

        # Goal line
        body.append(Text("目标: ", style="muted") + Text(goal_text[:100]))
        body.append("\n")

        # Progress bar
        bar = render_progress_bar(topic_done, topic_total)
        pct_display = f"{pct}%" if pct is not None else "--%"
        body.append(Text.from_markup(f"进度: {bar}  "))
        body.append(f"{topic_done}/{topic_total} ({pct_display})", style="highlight")
        body.append("\n")

        # Milestones
        ms_pct = (ms_done * 100 // ms_total) if ms_total > 0 else None
        ms_pct_display = f" ({ms_pct}%)" if ms_pct is not None else ""
        body.append(Text(f"里程碑: {ms_done}/{ms_total}{ms_pct_display}", style="muted"))
        body.append("\n")

        # Meta
        meta_parts = []
        if created_date != "—":
            meta_parts.append(f"创建: {created_date}")
        if est_hours != "—":
            meta_parts.append(f"预计: {est_hours}")
        if meta_parts:
            body.append(Text("  ".join(meta_parts), style="dim"))

        # ── Title bar ──
        title_parts = Text()
        title_parts.append(plan_name, style="learn.name")
        title_parts.append("  ")
        title_parts.append("[LEARN]", style="learn.type")
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

    # ── Summary table ──
    overall_pct = (total_done * 100 // total_topics) if total_topics > 0 else 0
    ms_overall_pct = (total_ms_done * 100 // total_ms) if total_ms > 0 else 0

    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_column(style="highlight", justify="right")
    summary_table.add_column()
    summary_table.add_row("总进度:", f"{total_done}/{total_topics} ({overall_pct}%)")
    summary_table.add_row("里程碑:", f"{total_ms_done}/{total_ms} ({ms_overall_pct}%)" if total_ms > 0 else "里程碑: —")
    summary_table.add_row("活跃计划:", str(len(plans)))
    console.print(Panel(summary_table, title="汇总", title_align="left", border_style="muted"))


if __name__ == "__main__":
    main()
