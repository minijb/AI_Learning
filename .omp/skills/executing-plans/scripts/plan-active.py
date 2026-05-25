#!/usr/bin/env python3
"""
plan-active.py — 展示所有活跃计划（rich multi-line card format）
输出使用 Unicode box-drawing 字符的多行卡片格式。
"""

import re
import sys
import shutil
from pathlib import Path

# Windows terminal UTF-8 support
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, get_progress_summary


def _read_file_safe(path: Path) -> str | None:
    """Read a text file, returning None on any error (missing, encoding, etc.)."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _extract_goal(exec_plan_content: str) -> str:
    """Extract the **Goal:** line from an exec-plan.md."""
    m = re.search(r'\*\*Goal:\*\*\s*(.+)$', exec_plan_content, re.M)
    if m:
        goal = m.group(1).strip()
        return goal[:120]
    return "（无目标摘要）"


def _parse_tasks_from_exec_plan(content: str) -> list[str]:
    """Parse ## Task N: titles from exec-plan.md."""
    return re.findall(r'^##\s+(Task\s+\d+)[ :]', content, re.M)


def _parse_task_status_from_progress(progress_content: str, task_labels: list[str]) -> dict[str, bool]:
    """Map task labels to done status from progress.txt lines like `- [x] Task 1 — ...`."""
    status: dict[str, bool] = {}
    for label in task_labels:
        # Match lines like "- [x] Task 1 — ..." or "- [ ] Task 1 — ..."
        pattern = rf'^-\s*\[([ x])\]\s+{re.escape(label)}\b'
        m = re.search(pattern, progress_content, re.M)
        status[label] = (m is not None and m.group(1) == 'x')
    return status


def _extract_blocked_lines(progress_content: str) -> list[str]:
    """Extract lines starting with '- [ ]' or '- [x]' that contain [BLOCKED]."""
    blocked = []
    for line in progress_content.splitlines():
        stripped = line.strip()
        if re.match(r'^-\s*\[[ x]\]', stripped) and '[BLOCKED]' in stripped:
            blocked.append(stripped)
    return blocked


def main():
    env = get_env()
    active_dir = env.active_dir

    if not active_dir.exists() or not active_dir.is_dir():
        print("没有活跃计划。")
        sys.exit(0)

    items = [p for p in active_dir.iterdir() if p.name != ".gitkeep"]
    # Filter out empty/stale directories (no recognizable plan files)
    items = [p for p in items if not p.is_dir() or
             any((p / f).exists() for f in ["exec-plan.md", "feature-list.json", "progress.txt"])]
    if not items:
        print("没有活跃计划。")
        sys.exit(0)

    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    box_width = max(min(cols, 80), 60)

    bar = "█"
    empty = "░"
    check = "✓"
    cross = "✗"

    total_done = 0
    total_all = 0
    total_blocked = 0

    for item in sorted(items):
        plan_name = item.stem if item.is_file() else item.name
        is_dir = item.is_dir()
        type_mark = "[FULL]" if is_dir else "[QUICK]"

        # ── exec-plan.md extraction ──
        goal_text = ""
        exec_tasks: list[str] = []
        if is_dir:
            exec_plan_path = item / "exec-plan.md"
            ep_content = _read_file_safe(exec_plan_path)
            if ep_content is None:
                goal_text = "（无 exec-plan.md）"
            else:
                # Check if it was an encoding error vs missing file
                if exec_plan_path.exists():
                    # File exists but read failed → encoding error
                    if not ep_content:  # read_text returned None
                        goal_text = "（编码错误）"
                    else:
                        goal_text = _extract_goal(ep_content)
                        exec_tasks = _parse_tasks_from_exec_plan(ep_content)
                else:
                    goal_text = "（无 exec-plan.md）"
        else:
            # QUICK plan (single .md file)
            content = _read_file_safe(item)
            if content is None:
                goal_text = "（编码错误）"
            else:
                goal_text = _extract_goal(content)
                exec_tasks = _parse_tasks_from_exec_plan(content)

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

        # ── Progress bar ──
        if feat_total > 0:
            pct = feat_done * 100 // feat_total
            filled = pct * 10 // 100
        else:
            pct = None
            filled = 0
        bar_str = bar * filled + empty * (10 - filled)
        pct_display = f"{pct}%" if pct is not None else "--%"

        # ── Task list ──
        task_parts: list[str] = []
        has_tasks_dir = is_dir and (item / "tasks").is_dir()
        if has_tasks_dir:
            tasks_dir = item / "tasks"
            task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == ".md"])
            for tf in task_files:
                tc = _read_file_safe(tf)
                if tc:
                    all_cb = len(re.findall(r'- \[.\]', tc))
                    done_cb = len(re.findall(r'- \[x\]', tc))
                    task_done_flag = (all_cb > 0 and done_cb >= all_cb)
                else:
                    task_done_flag = False
                label = tf.stem  # e.g. "task-01-project-scaffold"
                task_parts.append(f"{label} [{check if task_done_flag else cross}]")
        elif exec_tasks:
            # Parse from progress.txt
            progress_path = item / "progress.txt" if is_dir else None
            if is_dir and progress_path and progress_path.exists():
                pc = _read_file_safe(progress_path) or ""
                task_status = _parse_task_status_from_progress(pc, exec_tasks)
                for label in exec_tasks:
                    done_flag = task_status.get(label, False)
                    task_parts.append(f"{label} [{check if done_flag else cross}]")
            else:
                for label in exec_tasks:
                    task_parts.append(f"{label} [?]")

        # ── Blocked info ──
        blocked_info = ""
        if is_dir:
            progress_path = item / "progress.txt"
            if progress_path.exists():
                pc = _read_file_safe(progress_path) or ""
                blocked_lines = _extract_blocked_lines(pc)
                if blocked_lines:
                    # Show first blocked line, truncate
                    first = blocked_lines[0]
                    if len(first) > 60:
                        first = first[:57] + "..."
                    blocked_info = first
                else:
                    blocked_info = "无"
            else:
                blocked_info = "（无 progress.txt）"
        else:
            blocked_info = "（无 progress.txt）"

        # ── Render card ──
        # Title line
        title_left = f"┌─ {plan_name} "
        title_right = f" {type_mark} {status} ─┐"
        available_for_title = box_width - len(title_left) - len(title_right)
        dashes = "─" * max(available_for_title, 0)
        title_line = f"{title_left}{dashes}{title_right}"

        # Goal line
        goal_prefix = "│ 目标: "
        goal_max = box_width - len(goal_prefix) - 3  # 1 for │ at end (the prefix already has │)
        # Actually, the format is "│ 目标: <text>  │" with right padding
        goal_content = goal_text[:goal_max] if len(goal_text) > goal_max else goal_text
        goal_padding = " " * max(box_width - len(goal_prefix) - len(goal_content) - 1, 0)
        goal_line = f"{goal_prefix}{goal_content}{goal_padding}│"

        # Progress line
        prog_text = f"进度: {bar_str} {feat_done}/{feat_total} ({pct_display})"
        prog_padding = " " * max(box_width - len(prog_text) - 2, 0)
        prog_line = f"│ {prog_text}{prog_padding}│"

        # Task line
        tasks_text = "任务: " + " ".join(task_parts) if task_parts else "任务: （无任务数据）"
        if len(tasks_text) > box_width - 3:
            tasks_text = tasks_text[:box_width - 6] + "..."
        tasks_padding = " " * max(box_width - len(tasks_text) - 2, 0)
        tasks_line = f"│ {tasks_text}{tasks_padding}│"

        # Blocked line
        blocked_text = f"阻塞: {blocked_info}"
        if len(blocked_text) > box_width - 3:
            blocked_text = blocked_text[:box_width - 6] + "..."
        blocked_padding = " " * max(box_width - len(blocked_text) - 2, 0)
        blocked_line = f"│ {blocked_text}{blocked_padding}│"

        # Bottom line
        bottom_line = "└" + "─" * (box_width - 2) + "┘"

        print(title_line)
        print(goal_line)
        print(prog_line)
        print(tasks_line)
        print(blocked_line)
        print(bottom_line)
        print()

    # ── Summary ──
    sep = "─" * box_width
    print(sep)
    if total_all > 0:
        overall_pct = total_done * 100 // total_all
        print(f"总进度: {total_done}/{total_all} ({overall_pct}%)  |  阻塞: {total_blocked}  |  活跃计划: {len(items)}")
    else:
        print(f"总进度: 0/0 (0%)  |  阻塞: {total_blocked}  |  活跃计划: {len(items)}")


if __name__ == "__main__":
    main()
