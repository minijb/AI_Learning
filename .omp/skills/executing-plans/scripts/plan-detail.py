#!/usr/bin/env python3
"""
plan-detail.py <plan_name> — 检查具体计划的详细状态
输出 5 个分区：概览 / 功能点 / 任务进度 / 阻塞项 / 文件清单。
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, get_progress_summary, error_exit, warn, read_plan_json, get_console, \
    read_file_safe, extract_goal, extract_task_titles, extract_blocked_lines, parse_task_checkboxes
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich import box

sys.path.insert(0, str(Path(__file__).parents[3] / "lib"))
from _planning_common import _read_index_entries


def _fuzzy_search(query: str, items: list[Path]) -> list[Path]:
    """Fuzzy match query against directory/.md names. Returns sorted by priority."""
    q = query.lower()
    scored: list[tuple[int, Path]] = []
    for item in items:
        name = item.stem if item.is_file() else item.name
        name_low = name.lower()
        if name_low == q:
            scored.append((0, item))
        elif name_low.startswith(q):
            scored.append((1, item))
        elif q in name_low:
            scored.append((2, item))
    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored]


def _find_plan(plan_name: str, env) -> tuple[Optional[Path], str, Optional[str]]:
    """Search active_dir then completed_dir. Returns (path, source, matched_name)."""
    items_active = [p for p in env.active_dir.iterdir() if p.name != ".gitkeep"] if env.active_dir.exists() else []
    items_active = [p for p in items_active if not p.is_dir() or
                    any((p / f).exists() for f in ["exec-plan.md", "feature-list.json", "progress.txt"])]
    matches = _fuzzy_search(plan_name, items_active)

    if matches:
        if len(matches) == 1:
            item = matches[0]
            return item, "active", item.stem if item.is_file() else item.name
        lines = [f"找到 {len(matches)} 个匹配:"]
        for i, m in enumerate(matches[:5], 1):
            name = m.stem if m.is_file() else m.name
            lines.append(f"  {i}. {name}")
        if len(matches) > 5:
            lines.append(f"  ... 还有 {len(matches) - 5} 个")
        error_exit("\n".join(lines))

    items_completed = [p for p in env.completed_dir.iterdir() if p.name != ".gitkeep" and p.is_dir()] if env.completed_dir.exists() else []
    matches = _fuzzy_search(plan_name, items_completed)
    if matches:
        if len(matches) == 1:
            item = matches[0]
            return item, "completed", item.stem if item.is_file() else item.name
        lines = [f"找到 {len(matches)} 个匹配:"]
        for i, m in enumerate(matches[:5], 1):
            name = m.stem if m.is_file() else m.name
            lines.append(f"  {i}. {name}")
        if len(matches) > 5:
            lines.append(f"  ... 还有 {len(matches) - 5} 个")
        error_exit("\n".join(lines))

    index_path = env.plans_dir / "PLAN_COMPLETED.md"
    entries = _read_index_entries(index_path)
    q = plan_name.lower()
    for entry in entries:
        cells = entry["cells"]
        if len(cells) < 2:
            continue
        name = cells[1]
        if q in name.lower() or name.lower() == q:
            return None, "index_only", name
    return None, "", None


def _extract_meta(content: str) -> dict[str, str]:
    """Extract Goal, Architecture, Tech Stack from exec-plan.md content."""
    result = {}
    for key in ["Goal", "Architecture", "Tech Stack"]:
        m = re.search(rf'\*\*{key}:\*\*\s*(.+)$', content, re.M)
        result[key] = m.group(1).strip() if m else ""
    return result


def _get_completion_date(plan_dir: Path, env) -> Optional[str]:
    """Get completion date from *-summary.txt, PLAN_COMPLETED.md, or dir mtime."""
    sibling = env.completed_dir / f"{plan_dir.name}-summary.txt"
    if sibling.exists():
        sc = read_file_safe(sibling)
        if sc:
            m = re.search(r'完成日期[：:]\s*(.+)$', sc, re.M)
            if m:
                return m.group(1).strip()
    for f in plan_dir.iterdir():
        if f.suffix == ".txt" and f.stem.endswith("-summary"):
            sc = read_file_safe(f)
            if sc:
                m = re.search(r'完成日期[：:]\s*(.+)$', sc, re.M)
                if m:
                    return m.group(1).strip()
    index_path = env.plans_dir / "PLAN_COMPLETED.md"
    entries = _read_index_entries(index_path)
    for entry in entries:
        cells = entry["cells"]
        if len(cells) >= 2 and cells[1] == plan_dir.name:
            return cells[0] if len(cells) > 0 else None
    return datetime.fromtimestamp(plan_dir.stat().st_mtime).strftime('%Y-%m-%d')


def main():
    parser = argparse.ArgumentParser(description="查看具体计划的详细状态")
    parser.add_argument("plan_name", help="计划名称（支持模糊匹配）")
    args = parser.parse_args()

    env = get_env()
    console = get_console()
    plan_path, source, matched_name = _find_plan(args.plan_name, env)

    if plan_path is None and source != "index_only":
        error_exit(f"未找到计划: {args.plan_name}")

    # ── PLAN_COMPLETED.md only fallback ──
    if source == "index_only":
        index_path = env.plans_dir / "PLAN_COMPLETED.md"
        entries = _read_index_entries(index_path)
        entry_data = None
        for entry in entries:
            if len(entry["cells"]) >= 2 and entry["cells"][1] == matched_name:
                entry_data = entry
                break
        cells = entry_data["cells"] if entry_data else []
        date_str = cells[0] if len(cells) > 0 else "?"
        plan_type = cells[2] if len(cells) > 2 else "?"
        summary = cells[4] if len(cells) > 4 else ""

        title = Text()
        title.append(matched_name, style="plan.name")
        title.append(" [索引]")
        title.append(f" — COMPLETED ({date_str})")
        console.print(Panel(title, border_style="muted"))
        console.print()
        console.print(f"[highlight]类型:[/highlight] {plan_type}")
        console.print(f"[highlight]完成日期:[/highlight] {date_str}")
        console.print(f"[highlight]摘要:[/highlight] {summary if summary else '（无摘要）'}")
        console.print()
        console.print("[muted]（仅索引记录，无完整数据）[/muted]")
        return

    # ── Normal path: plan directory found ──
    is_active = source == "active"
    plan_dir = plan_path
    plan_name = matched_name

    # Read exec-plan.md
    exec_plan_path = plan_dir / "exec-plan.md"
    ep_error = None
    ep_content = None
    meta = {}
    task_titles = []

    if exec_plan_path.exists():
        ep_content = read_file_safe(exec_plan_path)
        if ep_content is None:
            ep_error = "（文件编码错误）"
        else:
            meta = _extract_meta(ep_content)
            task_titles = extract_task_titles(ep_content)
    else:
        ep_error = "（无 exec-plan.md）"

    # Read progress.txt
    progress_path = plan_dir / "progress.txt"
    progress_content = None
    progress_checkboxes = {}
    blocked_lines = []
    if progress_path.exists():
        progress_content = read_file_safe(progress_path)
        if progress_content:
            progress_checkboxes = parse_task_checkboxes(progress_content)
            blocked_lines = extract_blocked_lines(progress_content)

    # Read feature-list.json
    features = []
    feature_file = plan_dir / "feature-list.json"
    if feature_file.exists():
        data = read_plan_json(feature_file)
        if data:
            features = data.get("features", [])

    # Status
    summary = get_progress_summary(plan_dir)
    feat_total = summary["total"]
    feat_done = summary["done"]
    blocked_count = summary["blocked"]

    if is_active:
        if blocked_count > 0:
            status = "BLOCKED"
            status_style = "plan.status.blocked"
        elif feat_total > 0 and feat_done >= feat_total:
            status = "DONE"
            status_style = "plan.status.done"
        elif feat_done > 0:
            status = "IN_PROGRESS"
            status_style = "plan.status.progress"
        else:
            status = "PENDING"
            status_style = "plan.status.pending"
    else:
        completion_date = _get_completion_date(plan_dir, env)
        status = f"COMPLETED ({completion_date})" if completion_date else "COMPLETED"
        status_style = "success"

    is_dir = plan_dir.is_dir()
    type_mark = "FULL" if is_dir else "QUICK"

    # ═══════ Section 1: Overview ═══════
    overview = Table.grid(padding=(0, 1))
    overview.add_column(style="muted", justify="right")
    overview.add_column()

    title = Text()
    title.append(plan_name, style="plan.name")
    title.append(f"  [{type_mark}]")
    title.append(f"  {status}", style=status_style)

    console.print(Panel(title, border_style=status_style, box=box.HEAVY))
    console.print()

    if ep_error:
        console.print(f"[muted]{ep_error}[/muted]")
    else:
        if meta.get("Goal"):
            overview.add_row("目标:", meta["Goal"])
        if meta.get("Architecture"):
            overview.add_row("架构:", meta["Architecture"])
        if meta.get("Tech Stack"):
            overview.add_row("技术栈:", meta["Tech Stack"])

    if overview.row_count > 0:
        console.print(Panel(overview, title="概览", title_align="left", border_style="muted"))
        console.print()

    # ═══════ Section 2: Feature points ═══════
    if features:
        ft = Table(title="功能点", title_style="bold", box=box.SIMPLE, padding=(0, 1))
        ft.add_column("", width=2)
        ft.add_column("ID", style="cyan")
        ft.add_column("Category", style="dim")
        ft.add_column("Description")

        total = len(features)
        passed = sum(1 for f in features if f.get("passes") is True)
        display_count = min(total, 15)

        for f in features[:display_count]:
            mark = "[success]✓[/success]" if f.get("passes") else "[muted]✗[/muted]"
            desc = f.get("description", "")
            if len(desc) > 120:
                desc = desc[:117] + "..."
            ft.add_row(mark, f.get("id", "?"), f.get("category", ""), desc)

        if total > 15:
            ft.add_row("", "...", "", f"[muted]还有 {total - 15} 个功能点，详见 feature-list.json[/muted]")

        if total > 0:
            pct = passed * 100 // total
            ft.caption = f"通过: {passed}/{total} ({pct}%)"
            ft.caption_style = "highlight"
        console.print(Panel(ft, border_style="muted"))

    # ═══════ Section 3: Task progress ═══════
    tasks_dir = plan_dir / "tasks"
    has_tasks_dir = tasks_dir.is_dir()
    task_done_count = 0
    task_total_count = 0

    tt = Table(title="任务进度", title_style="bold", box=box.SIMPLE, padding=(0, 1))
    tt.add_column("", width=2)
    tt.add_column("任务")

    if has_tasks_dir:
        task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == ".md"])
        task_total_count = len(task_files)
        for tf in task_files:
            tc = read_file_safe(tf)
            if tc:
                all_cb = len(re.findall(r'- \[.\]', tc))
                done_cb = len(re.findall(r'- \[x\]', tc))
                done_flag = all_cb > 0 and done_cb >= all_cb
            else:
                done_flag = False
            if done_flag:
                task_done_count += 1
            mark = "[success]✓[/success]" if done_flag else "[muted]✗[/muted]"
            tt.add_row(mark, tf.stem)
    else:
        for label in task_titles:
            task_total_count += 1
            done_flag = False
            task_prefix = label.split(" — ")[0] if " — " in label else label
            for progress_label, is_done in progress_checkboxes.items():
                if progress_label.startswith(task_prefix):
                    done_flag = is_done
                    break
            if done_flag:
                task_done_count += 1
            mark = "[success]✓[/success]" if done_flag else "[muted]✗[/muted]"
            tt.add_row(mark, label)

        if not task_titles:
            tt.add_row("", "[muted]（无任务数据）[/muted]")

    if task_total_count > 0 or task_titles:
        tt.caption = f"任务完成: {task_done_count}/{task_total_count}"
        tt.caption_style = "highlight"
        console.print(Panel(tt, border_style="muted"))
        console.print()

    # ═══════ Section 4: Blocked items ═══════
    if progress_path.exists():
        bt = Table(title="阻塞项", title_style="bold", box=box.SIMPLE, padding=(0, 1))
        if blocked_lines:
            for line in blocked_lines:
                bt.add_row(Text(line, style="plan.status.blocked"))
        else:
            bt.add_row("[muted]无阻塞项[/muted]")
        console.print(Panel(bt, border_style="muted"))
        console.print()

    # ═══════ Section 5: File listing ═══════
    if is_dir:
        tree = Tree("文件", style="muted")
        all_files = sorted(plan_dir.rglob("*"), key=lambda p: (p.is_dir(), p.name))
        for f in all_files:
            if f.is_dir():
                continue
            rel = str(f.relative_to(plan_dir))
            tree.add(rel)

        # Count files
        file_count = sum(1 for f in all_files if not f.is_dir())
        console.print(Panel(tree, title=f"文件清单 ({file_count})", title_align="left", border_style="muted"))


if __name__ == "__main__":
    main()
