#!/usr/bin/env python3
"""
plan-completed.py — 展示所有已完成计划（Rich Panel 卡片格式）
从 completed_dir 目录和 PLAN_COMPLETED.md 两个数据源收集，按完成日期倒序排列。
"""

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, warn, read_plan_json, get_console, \
    read_file_safe, extract_goal
sys.path.insert(0, str(Path(__file__).parents[3] / "lib"))
from _planning_common import _read_index_entries
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box


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
        has_exec = (item / "exec-plan.md").exists()
        has_summary = any(f.suffix == ".txt" and f.stem.endswith("-summary") for f in item.iterdir())
        if not has_exec and not has_summary:
            continue

        plan_data = {"name": plan_name, "path": item, "type": "FULL", "source": "dir"}
        completion_date = None
        summary_text = "（摘要不可用）"

        summary_files: list[Path] = []
        for f in item.iterdir():
            if f.suffix == ".txt" and f.stem.endswith("-summary"):
                summary_files.append(f)
        sibling = completed_dir / f"{plan_name}-summary.txt"
        if sibling.exists():
            summary_files.append(sibling)

        for sf in sorted(summary_files, key=lambda f: f.stat().st_mtime, reverse=True):
            sc = read_file_safe(sf)
            if sc:
                if completion_date is None:
                    completion_date = _extract_completion_date_from_summary(sc)
                if summary_text == "（摘要不可用）":
                    for line in sc.splitlines():
                        stripped = line.strip()
                        if (stripped and not stripped.startswith("#") and
                            not stripped.startswith("计划:") and
                            not stripped.startswith("完成日期:") and
                            not stripped.startswith("归档时间:") and
                            not stripped.startswith("功能点完成情况:") and
                            not stripped.startswith("[x]") and
                            not stripped.startswith("[ ]")):
                            summary_text = stripped[:120]
                            break
            if completion_date is not None and summary_text != "（摘要不可用）":
                break

        if not completion_date:
            completion_date = datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d')
        plan_data["completion_date"] = completion_date

        if summary_text == "（摘要不可用）" and has_exec:
            ep_content = read_file_safe(item / "exec-plan.md")
            if ep_content:
                summary_text = extract_goal(ep_content)
        plan_data["summary"] = summary_text

        # Feature points
        feature_file = item / "feature-list.json"
        if feature_file.exists():
            data = read_plan_json(feature_file)
            if data:
                features = data.get("features", [])
                feat_parts = []
                total = len(features)
                passed = sum(1 for f in features if f.get("passes") is True)
                for i, f in enumerate(features[:6]):
                    mark = "[success]✓[/success]" if f.get("passes") else "[muted]✗[/muted]"
                    feat_parts.append(f"{mark} {f.get('id', '?')}")
                if len(features) > 6:
                    feat_parts.append(f"[muted]还有 {len(features) - 6} 个...[/muted]")
                plan_data["feature_parts"] = feat_parts
                plan_data["feature_total"] = total
                plan_data["feature_passed"] = passed
            else:
                plan_data["feature_parts"] = None
        else:
            plan_data["feature_parts"] = None

        results.append(plan_data)
    return results


def _collect_from_index() -> list[dict]:
    """Collect completed plans from PLAN_COMPLETED.md."""
    env = get_env()
    index_path = env.plans_dir / "PLAN_COMPLETED.md"
    entries = _read_index_entries(index_path)
    results = []
    for entry in entries:
        cells = entry["cells"]
        if len(cells) < 2:
            continue
        results.append({
            "name": cells[1],
            "completion_date": cells[0] if len(cells) > 0 else "",
            "type": cells[2] if len(cells) > 2 else "FULL",
            "summary": cells[4] if len(cells) > 4 else "（摘要不可用）",
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
            merged.append(ip)
    merged.sort(key=lambda p: p.get("completion_date", ""), reverse=True)
    return merged


def main():
    env = get_env()
    console = get_console()
    completed_dir = env.completed_dir

    dir_plans = _collect_from_completed_dir(completed_dir)
    index_plans = _collect_from_index()
    merged = _merge_plans(dir_plans, index_plans)

    if not merged:
        console.print("[warn]没有已完成计划。[/warn]")
        sys.exit(0)

    only_index = all(p["source"] == "index" for p in merged)

    if only_index:
        console.print("[heading]已完成计划（仅索引记录）：[/heading]")
        console.print()
        for p in merged:
            console.print(f"  {p['name']:<40} {p['completion_date']:<12} [[plan.type]{p['type']}[/plan.type]]")
        console.print()
        return

    for p in merged:
        plan_name = p["name"]
        plan_type = p["type"]
        comp_date = p["completion_date"]
        summary_text = p.get("summary", "（摘要不可用）")
        is_index_only = p["source"] == "index"

        if is_index_only:
            body = Text()
            body.append(f"类型: {plan_type}\n", style="plan.type")
            body.append(f"摘要: {summary_text[:120]}", style="muted")
            body.append("\n（仅索引记录，无完整数据）", style="muted")
            title = Text(plan_name, style="plan.name")
            title.append(f"  完成: {comp_date}")
            console.print(Panel(body, title=title, border_style="muted"))
            console.print()
            continue

        # Full card
        body_lines: list[Text] = []
        body_lines.append(Text(f"类型: ", style="muted") + Text(plan_type, style="plan.type"))
        body_lines.append(Text(f"摘要: ", style="muted") + Text(summary_text[:150]))

        feat_parts = p.get("feature_parts")
        if feat_parts:
            feat_text = Text("功能点: ", style="muted")
            for i, part in enumerate(feat_parts):
                if i > 0:
                    feat_text.append("  ")
                feat_text.append(Text.from_markup(part))
            feat_total = p.get("feature_total", 0)
            feat_passed = p.get("feature_passed", 0)
            if feat_total > 0:
                suffix = f" — 全部通过 ({feat_passed}/{feat_total})" if feat_passed >= feat_total else f" ({feat_passed}/{feat_total})"
                style = "success" if feat_passed >= feat_total else "warn"
                feat_text.append(suffix, style=style)
            body_lines.append(feat_text)

        body = Text()
        for i, line in enumerate(body_lines):
            if i > 0:
                body.append("\n")
            body.append(line)

        title = Text(plan_name, style="plan.name")
        title.append(f"  完成: {comp_date}", style="success")

        console.print(Panel(body, title=title, title_align="left", border_style="success", box=box.ROUNDED))
        console.print()


if __name__ == "__main__":
    main()
