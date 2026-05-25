#!/usr/bin/env python3
"""
plan-detail.py <plan_name> — 检查具体计划的详细状态
输出 5 段详细信息：概览 / 功能点 / 任务进度 / 阻塞项 / 文件清单。
"""

import argparse
import re
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Windows terminal UTF-8 support
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, get_progress_summary, error_exit, info, warn, read_plan_json
sys.path.insert(0, str(Path(__file__).parents[3] / "lib"))
from _planning_common import _read_index_entries


def _read_file_safe(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _fuzzy_search(query: str, items: list[Path]) -> list[Path]:
    """Fuzzy match query against directory/.md names. Returns sorted by priority."""
    q = query.lower()
    scored: list[tuple[int, Path]] = []

    for item in items:
        name = item.stem if item.is_file() else item.name
        name_low = name.lower()

        if name_low == q:
            scored.append((0, item))  # exact match
        elif name_low.startswith(q):
            scored.append((1, item))  # prefix match
        elif q in name_low:
            scored.append((2, item))  # substring match

    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored]


def _find_plan(plan_name: str, env) -> tuple[Path | None, str, str | None]:
    """Search active_dir then completed_dir. Returns (path, source, matched_name)."""
    items_active = [p for p in env.active_dir.iterdir() if p.name != ".gitkeep"] if env.active_dir.exists() else []
    matches = _fuzzy_search(plan_name, items_active)

    if matches:
        if len(matches) == 1:
            item = matches[0]
            return item, "active", item.stem if item.is_file() else item.name
        # Multi-match: list candidates
        lines = [f"找到 {len(matches)} 个匹配:"]
        for i, m in enumerate(matches[:5], 1):
            name = m.stem if m.is_file() else m.name
            lines.append(f"  {i}. {name}")
        if len(matches) > 5:
            lines.append(f"  ... 还有 {len(matches) - 5} 个")
        error_exit("\n".join(lines))

    # Try completed_dir
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

    # Try PLAN_COMPLETED.md as last resort
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


def _parse_task_titles(content: str) -> list[str]:
    """Parse ## Task N: titles from exec-plan.md."""
    tasks = []
    for m in re.finditer(r'^##\s+(Task\s+\d+)[ :]', content, re.M):
        # Try to also capture description after "—" or "："
        label = m.group(1)
        # Get the rest of the line after the match
        line_start = m.start()
        line_end = content.find('\n', m.end())
        if line_end == -1:
            line_end = len(content)
        rest = content[m.end():line_end].strip()
        # Strip leading "—" or "：" or ":"
        desc = re.sub(r'^[—：:]\s*', '', rest)
        if desc:
            label = f"{label} — {desc}"
        tasks.append(label)
    return tasks


def _parse_task_checkboxes(progress_content: str) -> dict[str, bool]:
    """Parse - [x]/- [ ] lines from progress.txt, return {task_label: done}."""
    status: dict[str, bool] = {}
    for line in progress_content.splitlines():
        m = re.match(r'^-\s*\[([ x])\]\s+(.+)', line)
        if m:
            done = m.group(1) == 'x'
            label = m.group(2).strip()
            status[label] = done
    return status


def _extract_blocked_lines(progress_content: str) -> list[str]:
    """Extract lines with [BLOCKED] from progress.txt."""
    blocked = []
    for line in progress_content.splitlines():
        stripped = line.strip()
        if re.match(r'^-\s*\[[ x]\]', stripped) and '[BLOCKED]' in stripped:
            blocked.append(stripped)
    return blocked


def _get_completion_date(plan_dir: Path, env) -> str | None:
    """Get completion date from *-summary.txt, PLAN_COMPLETED.md, or dir mtime."""
    # Check sibling summary at completed_dir level
    sibling = env.completed_dir / f"{plan_dir.name}-summary.txt"
    if sibling.exists():
        sc = _read_file_safe(sibling)
        if sc:
            m = re.search(r'完成日期[：:]\s*(.+)$', sc, re.M)
            if m:
                return m.group(1).strip()

    # Check inside plan dir
    for f in plan_dir.iterdir():
        if f.suffix == ".txt" and f.stem.endswith("-summary"):
            sc = _read_file_safe(f)
            if sc:
                m = re.search(r'完成日期[：:]\s*(.+)$', sc, re.M)
                if m:
                    return m.group(1).strip()

    # PLAN_COMPLETED.md fallback
    index_path = env.plans_dir / "PLAN_COMPLETED.md"
    entries = _read_index_entries(index_path)
    for entry in entries:
        cells = entry["cells"]
        if len(cells) >= 2 and cells[1] == plan_dir.name:
            return cells[0] if len(cells) > 0 else None

    # Dir mtime
    return datetime.fromtimestamp(plan_dir.stat().st_mtime).strftime('%Y-%m-%d')


def main():
    parser = argparse.ArgumentParser(description="查看具体计划的详细状态")
    parser.add_argument("plan_name", help="计划名称（支持模糊匹配）")
    args = parser.parse_args()

    env = get_env()
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

        try:
            cols = shutil.get_terminal_size().columns
        except Exception:
            cols = 80
        box_width = max(min(cols, 80), 60)

        cells = entry_data["cells"] if entry_data else []
        date_str = cells[0] if len(cells) > 0 else "?"
        plan_type = cells[2] if len(cells) > 2 else "?"
        summary = cells[4] if len(cells) > 4 else ""

        print("╔" + "═" * (box_width - 2) + "╗")
        header = f"  {matched_name} [索引] — COMPLETED ({date_str})"
        header_pad = " " * max(box_width - len(header) - 3, 0)
        print(f"║ {header}{header_pad}║")
        print("╚" + "═" * (box_width - 2) + "╝")
        print()
        print(f"类型: {plan_type}")
        print(f"完成日期: {date_str}")
        print(f"摘要: {summary if summary else '（无摘要）'}")
        print()
        print("（仅索引记录，无完整数据）")
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
        ep_content = _read_file_safe(exec_plan_path)
        if ep_content is None:
            ep_error = "（文件编码错误）"
        else:
            meta = _extract_meta(ep_content)
            task_titles = _parse_task_titles(ep_content)
    else:
        ep_error = "（无 exec-plan.md）"

    # Read progress.txt
    progress_path = plan_dir / "progress.txt"
    progress_content = None
    progress_checkboxes = {}
    blocked_lines = []
    if progress_path.exists():
        progress_content = _read_file_safe(progress_path)
        if progress_content:
            progress_checkboxes = _parse_task_checkboxes(progress_content)
            blocked_lines = _extract_blocked_lines(progress_content)

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
        elif feat_total > 0 and feat_done >= feat_total:
            status = "DONE"
        elif feat_done > 0:
            status = "IN_PROGRESS"
        else:
            status = "PENDING"
    else:
        status = "COMPLETED"
        completion_date = _get_completion_date(plan_dir, env)
        if completion_date:
            status = f"COMPLETED ({completion_date})"

    # Terminal width
    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    box_width = max(min(cols, 80), 60)

    check = "✓"
    cross = "✗"

    # ═══════ Section 1: Overview ═══════
    is_dir = plan_dir.is_dir()
    type_mark = "[FULL]" if is_dir else "[QUICK]"

    print("╔" + "═" * (box_width - 2) + "╗")
    header = f"  {plan_name} {type_mark} — 状态: {status}"
    header_pad = " " * max(box_width - len(header) - 3, 0)
    print(f"║ {header}{header_pad}║")
    print("╚" + "═" * (box_width - 2) + "╝")
    print()

    if ep_error:
        print(ep_error)
    else:
        if meta.get("Goal"):
            print(f"目标: {meta['Goal']}")
        if meta.get("Architecture"):
            print(f"架构: {meta['Architecture']}")
        if meta.get("Tech Stack"):
            print(f"技术栈: {meta['Tech Stack']}")
    print()

    # ═══════ Section 2: Feature points ═══════
    if features:
        sep = "─" * 60
        print(f"{sep}")
        print("── 功能点 " + "─" * 52)
        print()

        total = len(features)
        passed = sum(1 for f in features if f.get("passes") is True)
        display_count = min(total, 10)

        for f in features[:display_count]:
            mark = check if f.get("passes") else cross
            desc = f.get("description", "")
            if len(desc) > 100:
                desc = desc[:97] + "..."
            print(f"[{mark}] {f.get('id', '?')} {f.get('category', '')}: {desc}")

        if total > 10:
            print(f"... 还有 {total - 10} 个功能点，详见 feature-list.json")

        if total > 0:
            pct = passed * 100 // total
            print(f"\n通过: {passed}/{total} ({pct}%)")
        else:
            print("\n通过: --/0 (--%)")
        print()
    elif feature_file.exists():
        # File exists but features is empty array
        pass  # skip the section
    # else: file doesn't exist, skip

    # ═══════ Section 3: Task progress ═══════
    tasks_dir = plan_dir / "tasks"
    has_tasks_dir = tasks_dir.is_dir()

    sep = "─" * 60
    print(f"{sep}")
    print("── 任务进度 " + "─" * 50)
    print()

    task_done_count = 0
    task_total_count = 0

    if has_tasks_dir:
        task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == ".md"])
        task_total_count = len(task_files)
        for tf in task_files:
            tc = _read_file_safe(tf)
            if tc:
                all_cb = len(re.findall(r'- \[.\]', tc))
                done_cb = len(re.findall(r'- \[x\]', tc))
                done_flag = all_cb > 0 and done_cb >= all_cb
            else:
                done_flag = False
            if done_flag:
                task_done_count += 1
            mark = check if done_flag else cross
            label = tf.stem
            print(f"[{mark}] {label}")
    else:
        # Use progress.txt checkboxes with task_titles from exec-plan.md
        for label in task_titles:
            task_total_count += 1
            # Try to match by prefix (Task N)
            done_flag = False
            for progress_label, is_done in progress_checkboxes.items():
                # Match if progress label starts with the task prefix
                task_prefix = label.split(" — ")[0] if " — " in label else label
                if progress_label.startswith(task_prefix):
                    done_flag = is_done
                    break
            if done_flag:
                task_done_count += 1
            mark = check if done_flag else cross
            print(f"[{mark}] {label}")

        if not task_titles:
            print("（无任务数据）")

    if task_total_count > 0:
        print(f"\n任务完成: {task_done_count}/{task_total_count}")
    print()

    # ═══════ Section 4: Blocked items ═══════
    if progress_path.exists():
        print(f"{sep}")
        print("── 阻塞项 " + "─" * 53)
        print()

        if blocked_lines:
            for line in blocked_lines:
                print(f"  {line}")
        else:
            print("无阻塞项")
        print()
    # else: progress.txt doesn't exist, skip section

    # ═══════ Section 5: File listing ═══════
    if is_dir:
        print(f"{sep}")
        print("── 文件 " + "─" * 55)
        print()

        all_files = sorted(plan_dir.rglob("*"), key=lambda p: (p.is_dir(), p.name))
        file_names = []
        for f in all_files:
            if f.is_dir():
                continue
            rel = f.relative_to(plan_dir)
            file_names.append(str(rel))

        # Print horizontally when width allows
        if file_names:
            line_parts = []
            current_line = ""
            for name in file_names:
                if not current_line:
                    current_line = name
                elif len(current_line) + len(name) + 4 <= box_width:
                    current_line += "    " + name
                else:
                    line_parts.append(current_line)
                    current_line = name
            if current_line:
                line_parts.append(current_line)
            for lp in line_parts:
                print(lp)
        else:
            print("（无文件）")
        print()


if __name__ == "__main__":
    main()
