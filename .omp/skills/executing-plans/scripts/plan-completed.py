#!/usr/bin/env python3
"""
plan-completed.py — 展示所有已完成计划（rich multi-line card format）
从 completed_dir 目录和 PLAN_COMPLETED.md 两个数据源收集，按完成日期倒序排列。
"""

import re
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Windows terminal UTF-8 support
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, info, warn, read_plan_json
sys.path.insert(0, str(Path(__file__).parents[3] / "lib"))
from _planning_common import _read_index_entries


def _read_file_safe(path: Path) -> str | None:
    """Read a text file, returning None on any error."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _extract_goal(exec_plan_content: str) -> str:
    """Extract **Goal:** line, truncated to 120 chars."""
    m = re.search(r'\*\*Goal:\*\*\s*(.+)$', exec_plan_content, re.M)
    if m:
        return m.group(1).strip()[:120]
    return "（无目标摘要）"


def _extract_completion_date_from_summary(content: str) -> str | None:
    """Extract 完成日期 from *-summary.txt."""
    m = re.search(r'完成日期[：:]\s*(.+)$', content, re.M)
    if m:
        return m.group(1).strip()
    return None


def _collect_from_completed_dir(completed_dir: Path) -> list[dict]:
    """Collect completed plans from completed_dir directories."""
    results = []
    if not completed_dir.exists() or not completed_dir.is_dir():
        return results

    for item in sorted(completed_dir.iterdir()):
        if item.name == ".gitkeep" or not item.is_dir():
            continue

        plan_name = item.name
        # Only process directories that have exec-plan.md or *-summary.txt
        has_exec = (item / "exec-plan.md").exists()
        has_summary = any(f.suffix == ".txt" and f.stem.endswith("-summary") for f in item.iterdir())

        if not has_exec and not has_summary:
            continue

        plan_data = {
            "name": plan_name,
            "path": item,
            "type": "FULL",
            "source": "dir",
        }

        # Completion date + summary: check both inside plan dir and sibling at completed_dir level
        completion_date = None
        summary_text = "（摘要不可用）"

        summary_files: list[Path] = []
        # Inside plan dir
        for f in item.iterdir():
            if f.suffix == ".txt" and f.stem.endswith("-summary"):
                summary_files.append(f)
        # Sibling at completed_dir level
        sibling = completed_dir / f"{plan_name}-summary.txt"
        if sibling.exists():
            summary_files.append(sibling)

        for sf in sorted(summary_files, key=lambda f: f.stat().st_mtime, reverse=True):
            sc = _read_file_safe(sf)
            if sc:
                if completion_date is None:
                    completion_date = _extract_completion_date_from_summary(sc)
                if summary_text == "（摘要不可用）":
                    lines = [l.strip() for l in sc.splitlines()
                             if l.strip() and not l.strip().startswith("#")]
                    for line in lines:
                        if (not line.startswith("计划:") and
                            not line.startswith("完成日期:") and
                            not line.startswith("归档时间:") and
                            not line.startswith("功能点完成情况:") and
                            not line.startswith("[x]") and
                            not line.startswith("[ ]")):
                            summary_text = line[:120]
                            break
            if completion_date is not None and summary_text != "（摘要不可用）":
                break

        if not completion_date:
            # Fallback to directory mtime
            completion_date = datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d')
        plan_data["completion_date"] = completion_date

        # Fallback to exec-plan.md Goal
        if summary_text == "（摘要不可用）" and has_exec:
            ep_content = _read_file_safe(item / "exec-plan.md")
            if ep_content:
                summary_text = _extract_goal(ep_content)

        plan_data["summary"] = summary_text

        # Feature points from feature-list.json
        feature_file = item / "feature-list.json"
        if feature_file.exists():
            data = read_plan_json(feature_file)
            if data:
                features = data.get("features", [])
                feat_parts = []
                total = len(features)
                passed = sum(1 for f in features if f.get("passes") is True)
                display_count = min(len(features), 6)
                for i, f in enumerate(features[:display_count]):
                    mark = "✓" if f.get("passes") else "✗"
                    feat_parts.append(f"[{mark}] {f.get('id', '?')}")
                if len(features) > 6:
                    feat_parts.append(f"还有 {len(features) - 6} 个...")
                plan_data["feature_parts"] = feat_parts
                plan_data["feature_total"] = total
                plan_data["feature_passed"] = passed
            else:
                plan_data["feature_parts"] = None
        else:
            plan_data["feature_parts"] = None

        results.append(plan_data)

    return results


def _collect_from_index(completed_dir: Path) -> list[dict]:
    """Collect completed plans from PLAN_COMPLETED.md, supplementing dir data."""
    env = get_env()
    index_path = env.plans_dir / "PLAN_COMPLETED.md"
    entries = _read_index_entries(index_path)

    results = []
    for entry in entries:
        cells = entry["cells"]
        # PLAN_COMPLETED.md columns: 完成日期 | 计划名 | 类型 | 主题 | 摘要
        if len(cells) < 2:
            continue
        date_str = cells[0] if len(cells) > 0 else ""
        name = cells[1] if len(cells) > 1 else ""
        plan_type = cells[2] if len(cells) > 2 else "FULL"
        summary_str = cells[4] if len(cells) > 4 else ""

        if not name:
            continue

        results.append({
            "name": name,
            "completion_date": date_str,
            "type": plan_type,
            "summary": summary_str if summary_str else "（摘要不可用）",
            "source": "index",
            "feature_parts": None,
        })

    return results


def _merge_plans(dir_plans: list[dict], index_plans: list[dict]) -> list[dict]:
    """Merge plans, prioritizing dir data over index data."""
    dir_names = {p["name"] for p in dir_plans}
    merged = list(dir_plans)

    for ip in index_plans:
        if ip["name"] not in dir_names:
            # Only include index-only plans as fallback
            merged.append(ip)

    # Sort by completion date descending
    def sort_key(p):
        d = p.get("completion_date", "")
        return d

    merged.sort(key=sort_key, reverse=True)
    return merged


def main():
    env = get_env()
    completed_dir = env.completed_dir

    dir_plans = _collect_from_completed_dir(completed_dir)
    index_plans = _collect_from_index(completed_dir)
    merged = _merge_plans(dir_plans, index_plans)

    if not merged:
        print("没有已完成计划。")
        sys.exit(0)

    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    box_width = max(min(cols, 80), 60)

    check = "✓"
    cross = "✗"

    # If only index entries (no dir data), show simple table
    only_index = all(p["source"] == "index" for p in merged)

    if only_index:
        print("已完成计划（仅索引记录）：")
        print()
        for p in merged:
            print(f"  {p['name']:<40} {p['completion_date']:<12} [{p['type']}]")
        print()
        return

    for p in merged:
        plan_name = p["name"]
        plan_type = p["type"]
        comp_date = p["completion_date"]
        summary_text = p["summary"]
        is_index_only = p["source"] == "index"

        if is_index_only:
            # Simple one-line for index-only entries
            print(f"┌─ {plan_name} ──────────────────── 完成: {comp_date} ────────────┐")
            print(f"│ 类型: {plan_type}                                              │")
            print(f"│ 摘要: {summary_text[:box_width - 5]}                           │")
            print(f"│ （仅索引记录，无完整数据）                                     │")
            print("└" + "─" * (box_width - 2) + "┘")
            print()
            continue

        # Full card for dir-based entries
        type_mark = f"[{plan_type}]"

        # Title line
        title_left = f"┌─ {plan_name} "
        title_right = f" 完成: {comp_date} ─┐"
        available = box_width - len(title_left) - len(title_right)
        dashes = "─" * max(available, 0)
        title_line = f"{title_left}{dashes}{title_right}"

        # Type line
        type_text = f"类型: {plan_type}"
        type_padding = " " * max(box_width - len(type_text) - 2, 0)
        type_line = f"│ {type_text}{type_padding}│"

        # Summary line(s)
        summary_prefix = "│ 摘要: "
        max_summary_len = box_width - len(summary_prefix) - 2
        if len(summary_text) > max_summary_len:
            # Split across two lines
            first_chunk = summary_text[:max_summary_len]
            first_padding = " " * max(box_width - len(summary_prefix) - len(first_chunk) - 1, 0)
            print(f"{title_line}")
            print(f"{type_line}")
            print(f"{summary_prefix}{first_chunk}{first_padding}│")
            remaining = summary_text[max_summary_len:]
            second_prefix = "│        "
            second_max = box_width - len(second_prefix) - 1
            second_chunk = remaining[:second_max]
            second_padding = " " * max(box_width - len(second_prefix) - len(second_chunk) - 1, 0)
            print(f"{second_prefix}{second_chunk}{second_padding}│")
        else:
            summary_padding = " " * max(box_width - len(summary_prefix) - len(summary_text) - 1, 0)
            print(f"{title_line}")
            print(f"{type_line}")
            print(f"{summary_prefix}{summary_text}{summary_padding}│")

        # Feature points line
        feat_parts = p.get("feature_parts")
        if feat_parts:
            feat_text = "功能点: " + " ".join(feat_parts)
            feat_total = p.get("feature_total", 0)
            feat_passed = p.get("feature_passed", 0)
            if feat_total > 0:
                status_suffix = f" — 全部通过 ({feat_passed}/{feat_total})" if feat_passed >= feat_total else f" ({feat_passed}/{feat_total})"
                feat_text += status_suffix

            if len(feat_text) > box_width - 3:
                feat_text = feat_text[:box_width - 6] + "..."
            feat_padding = " " * max(box_width - len(feat_text) - 2, 0)
            print(f"│ {feat_text}{feat_padding}│")

        # Bottom line
        print("└" + "─" * (box_width - 2) + "┘")
        print()


if __name__ == "__main__":
    main()
