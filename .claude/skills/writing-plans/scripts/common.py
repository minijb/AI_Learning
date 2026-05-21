#!/usr/bin/env python3
"""
Planning System — Python Common Library
All scripts share this module for env init, path utils, logging, JSON ops, etc.

⚠️ 本文件与 .claude/skills/executing-plans/scripts/common.py 内容完全同步。
   修改时请同时更新另一份副本，避免版本漂移。
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path




# ============================================================
# Initialization
# ============================================================

class PlanningEnv:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        if self._initialized:
            return
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True
            )
            self.repo_root = Path(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Not in a git repo — use current working directory as project root
            self.repo_root = Path.cwd()

        self.plans_dir = self.repo_root / "docs" / "exec-plans"
        self.scripts_dir = Path(__file__).parent.resolve()
        self.templates_dir = self.scripts_dir.parent / "templates"

        # Ensure directories exist
        (self.plans_dir / "active").mkdir(parents=True, exist_ok=True)
        (self.plans_dir / "completed").mkdir(parents=True, exist_ok=True)

        self._initialized = True

    @property
    def active_dir(self):
        self.initialize()
        return self.plans_dir / "active"

    @property
    def completed_dir(self):
        self.initialize()
        return self.plans_dir / "completed"


def get_env() -> PlanningEnv:
    env = PlanningEnv()
    env.initialize()
    return env


# ============================================================
# Logging (success is silent, failure outputs with fix hint)
# ============================================================

def info(msg: str):
    print(f"[INFO] {msg}")


def warn(msg: str):
    print(f"[WARN] {msg}")


def error(msg: str, fix: str = ""):
    print(f"[ERROR] {msg}", file=sys.stderr)
    if fix:
        print(f"  → 修复: {fix}", file=sys.stderr)


def error_exit(msg: str, fix: str = ""):
    error(msg, fix)
    sys.exit(1)


# ============================================================
# JSON Operations
# ============================================================

def read_plan_json(path: Path | str) -> dict | None:
    path = Path(path)
    if not path.exists():
        error(f"文件不存在: {path}", "检查路径是否正确")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        error(f"JSON 解析失败: {path}", f"检查 JSON 语法。错误: {e}")
        return None


def test_json_field_modification(original: dict, current: dict) -> list[str]:
    violations = []
    orig_map = {f["id"]: f for f in original.get("features", [])}
    curr_map = {f["id"]: f for f in current.get("features", [])}
    for fid, orig in orig_map.items():
        curr = curr_map.get(fid)
        if not curr:
            continue
        if curr.get("description") != orig.get("description"):
            violations.append(f"[{fid}] description 字段被修改（只允许修改 passes）")
        if curr.get("steps") != orig.get("steps"):
            violations.append(f"[{fid}] steps 字段被修改（只允许修改 passes）")
        if curr.get("category") != orig.get("category"):
            violations.append(f"[{fid}] category 字段被修改（只允许修改 passes）")
    return violations


# ============================================================
# File Operations
# ============================================================

def copy_plan_template(template_name: str, dest_path: Path | str) -> bool:
    env = get_env()
    src = env.templates_dir / template_name
    if not src.exists():
        error(f"模板不存在: {template_name}", "确保技能目录下 templates/ 目录中包含此模板")
        return False
    import shutil
    shutil.copy2(src, dest_path)
    return True


def sanitize_name(name: str) -> str:
    """Replace filesystem-illegal chars, preserve Unicode."""
    safe = re.sub(r'[\\/:*?"<>|]', "-", name)
    safe = re.sub(r"-+", "-", safe)
    safe = safe.strip("-")
    if not safe:
        from datetime import datetime
        safe = datetime.now().strftime("plan-%Y%m%d-%H%M%S")
    return safe


# ============================================================
# Progress Summary
# ============================================================

def get_progress_summary(plan_dir: Path | str) -> dict:
    plan_dir = Path(plan_dir)
    summary = {"total": 0, "done": 0, "blocked": 0}

    feature_file = plan_dir / "feature-list.json"
    if feature_file.exists():
        data = read_plan_json(feature_file)
        if data:
            features = data.get("features", [])
            summary["total"] = len(features)
            summary["done"] = sum(1 for f in features if f.get("passes") is True)

    progress_file = plan_dir / "progress.txt"
    if progress_file.exists():
        content = progress_file.read_text(encoding="utf-8")
        summary["blocked"] = content.count("[BLOCKED]")

    return summary


# ============================================================
# Index File Operations (PLAN.md / PLAN_COMPLETED.md)
# ============================================================

# Sentinel rows that mark unfilled templates
_PLACEHOLDER_REGEX = re.compile(r"^\|\s*—\s*\|")


def init_index_files():
    """Initialize PLAN.md and PLAN_COMPLETED.md from templates if they don't exist."""
    env = get_env()
    plan_index = env.plans_dir / "PLAN.md"
    completed_index = env.plans_dir / "PLAN_COMPLETED.md"

    if not plan_index.exists():
        src = env.templates_dir / "plan-index.md"
        if src.exists():
            import shutil
            shutil.copy2(src, plan_index)
            info(f"已初始化: {plan_index}")

    if not completed_index.exists():
        src = env.templates_dir / "plan-completed-index.md"
        if src.exists():
            import shutil
            shutil.copy2(src, completed_index)
            info(f"已初始化: {completed_index}")


def _read_index_lines(path: Path) -> list[str]:
    """Read index file lines. Return empty list if file doesn't exist."""
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _find_table_insert_point(lines: list[str], section_marker: str, table_header_pattern: str) -> int:
    """Find the insert position for a new row in a Markdown table section.

    Returns the line index where a new row should be inserted.
    If a placeholder row exists at the insert position, returns that index
    (caller should replace it).
    """
    in_section = False
    header_found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and section_marker in stripped:
            in_section = True
            continue
        if not in_section:
            continue
        if re.search(table_header_pattern, stripped):
            header_found = True
            continue
        if header_found and re.match(r"^\|[-:| ]+\|$", stripped):
            # This is the separator row; the next line is the insert position
            insert_at = i + 1
            # If next line is a placeholder, we'll replace it (return this index)
            # If not, we insert before existing entries
            return insert_at
    return -1


def _parse_index_entries(lines: list[str]) -> dict:
    """Parse PLAN.md into structured data.
    Returns {'task_groups': [...], 'independent': [...]}
    """
    result = {"task_groups": [], "independent": []}
    current_section = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and "任务组" in stripped:
            current_section = "task_group"
            continue
        elif stripped.startswith("## ") and "独立任务" in stripped:
            current_section = "independent"
            continue
        if not current_section:
            continue
        if not stripped.startswith("|") or stripped.startswith("|-"):
            continue
        if _PLACEHOLDER_REGEX.match(stripped):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]
        if current_section == "task_group":
            if len(cells) >= 6:
                # Also skip header row
                if cells[0] == "序号":
                    continue
                dep_val = cells[4] if len(cells) > 4 else ""
                if dep_val == "—" or not dep_val:
                    dep_val = ""
                result["task_groups"].append({
                    "name": cells[1],
                    "type": cells[2],
                    "summary": cells[3],
                    "depends": dep_val,
                    "status": cells[5] if len(cells) > 5 else "TODO",
                })
        elif current_section == "independent":
            if len(cells) >= 4:
                if cells[0] == "计划名":
                    continue
                result["independent"].append({
                    "name": cells[0],
                    "type": cells[1],
                    "summary": cells[2],
                    "status": cells[3] if len(cells) > 3 else "TODO",
                })
    return result


def _topological_sort(entries: list[dict]) -> list[dict]:
    """Sort task group entries topologically by dependency order."""
    if not entries:
        return []
    name_to_entry = {e["name"]: e for e in entries}
    sorted_entries = []
    visited = set()
    remaining = list(entries)
    while remaining:
        added = False
        still_remaining = []
        for e in remaining:
            deps = [d.strip() for d in e["depends"].split(",")] if e["depends"] else []
            if all(d in visited for d in deps if d):
                sorted_entries.append(e)
                visited.add(e["name"])
                added = True
            else:
                still_remaining.append(e)
        remaining = still_remaining
        if not added and remaining:
            sorted_entries.extend(remaining)
            break
    return sorted_entries


def _rebuild_plan_index(lines: list[str], data: dict):
    """Rebuild the task group and independent task tables in lines from data.
    Modifies lines in place."""
    # Find section boundaries
    tg_start = -1
    tg_end = -1
    indep_start = -1
    indep_end = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and "任务组" in stripped:
            tg_start = i
        elif stripped.startswith("## ") and "独立任务" in stripped:
            indep_start = i
            if tg_start >= 0 and tg_end < 0:
                tg_end = i
    if indep_start >= 0:
        indep_end = len(lines)  # end at EOF

    if tg_start < 0 or indep_start < 0:
        return

    # Find the end of task group section (before the --- before independent)
    for i in range(tg_start + 1, indep_start):
        if lines[i].strip() == "---":
            tg_end = i
            break
    if tg_end < 0:
        tg_end = indep_start

    # Find the end of independent section
    for i in range(indep_start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## ") and "独立任务" not in stripped:
            indep_end = i
            break
        if stripped == "---" and i > indep_start:
            # Check if this is the closing --- for the file
            next_non_empty = ""
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    next_non_empty = lines[j].strip()
                    break
            if next_non_empty.startswith("> "):
                indep_end = i
                break

    # Rebuild task group table
    tg_entries = _topological_sort(data["task_groups"])
    tg_lines = []
    tg_lines.append("## 任务组（有先后依赖的计划链）\n")
    tg_lines.append("\n")
    tg_lines.append("> 计划之间存在顺序依赖关系，排列顺序即为执行顺序。\n")
    tg_lines.append("\n")
    tg_lines.append("| 序号 | 计划名 | 类型 | 摘要 | 依赖 | 状态 |\n")
    tg_lines.append("|------|--------|------|------|------|------|\n")
    if tg_entries:
        for seq, e in enumerate(tg_entries, 1):
            dep_display = e["depends"] if e["depends"] else "—"
            tg_lines.append(f"| {seq} | {e['name']} | {e['type']} | {e['summary']} | {dep_display} | {e['status']} |\n")
    else:
        tg_lines.append("| — | — | — | — | — | — |\n")
    tg_lines.append("\n")
    tg_lines.append("<!-- 依赖列填写依赖的计划名，多个用逗号分隔。无依赖填 `—` -->\n")

    # Rebuild independent tasks table
    indep_entries = data["independent"]
    indep_lines = []
    indep_lines.append("## 独立任务（无依赖，可并行）\n")
    indep_lines.append("\n")
    indep_lines.append("> 这些计划与其他计划无依赖关系，可按任意顺序执行。\n")
    indep_lines.append("\n")
    indep_lines.append("| 计划名 | 类型 | 摘要 | 状态 |\n")
    indep_lines.append("|--------|------|------|------|\n")
    if indep_entries:
        for e in indep_entries:
            indep_lines.append(f"| {e['name']} | {e['type']} | {e['summary']} | {e['status']} |\n")
    else:
        indep_lines.append("| — | — | — | — |\n")

    # Replace sections
    new_lines = lines[:tg_start] + tg_lines + ["---\n", "\n"] + indep_lines + lines[indep_end:]
    lines.clear()
    lines.extend(new_lines)


def add_to_plan_index(plan_name: str, plan_type: str, summary: str,
                      depends: str = "", status: str = "TODO"):
    """Add a plan entry to PLAN.md.

    If 'depends' is non-empty, adds to the task group table and auto-promotes
    any dependency currently in independent tasks.
    Otherwise adds to the independent tasks table.
    Uses a rebuild approach to avoid duplicate entries.
    """
    env = get_env()
    plan_index = env.plans_dir / "PLAN.md"

    if not plan_index.exists():
        init_index_files()

    lines = _read_index_lines(plan_index)
    if not lines:
        warn("PLAN.md 不存在且无法初始化")
        return False

    data = _parse_index_entries(lines)

    # Determine dependency names to promote
    dep_names = []
    if depends and depends.strip() and depends.strip() != "—":
        dep_names = [d.strip() for d in depends.split(",") if d.strip()]

    new_entry = {
        "name": plan_name,
        "type": plan_type,
        "summary": summary,
        "depends": depends if depends and depends.strip() != "—" else "",
        "status": status,
    }

    if dep_names:
        # Move any dependency from independent to task group
        for dep_name in dep_names:
            for i, e in enumerate(data["independent"]):
                if e["name"] == dep_name:
                    data["task_groups"].append({
                        "name": e["name"],
                        "type": e["type"],
                        "summary": e["summary"],
                        "depends": "",
                        "status": e["status"],
                    })
                    data["independent"].pop(i)
                    break
        # Remove existing entries for this plan (avoid duplicates) and add new
        data["task_groups"] = [e for e in data["task_groups"] if e["name"] != plan_name]
        data["task_groups"].append(new_entry)
    else:
        # Independent task — remove from task_groups if present, add to independent
        data["task_groups"] = [e for e in data["task_groups"] if e["name"] != plan_name]
        data["independent"] = [e for e in data["independent"] if e["name"] != plan_name]
        data["independent"].append(new_entry)

    _rebuild_plan_index(lines, data)
    plan_index.write_text("".join(lines), encoding="utf-8")
    info(f"已添加到 PLAN.md: {plan_name}")
    return True


def _remove_from_plan_index(plan_name: str) -> bool:
    """Remove a plan entry from PLAN.md by plan name. Uses rebuild approach."""
    env = get_env()
    plan_index = env.plans_dir / "PLAN.md"

    if not plan_index.exists():
        return False

    lines = _read_index_lines(plan_index)
    if not lines:
        return False

    data = _parse_index_entries(lines)
    found = False

    for i, e in enumerate(data["task_groups"]):
        if e["name"] == plan_name:
            data["task_groups"].pop(i)
            found = True
            break

    if not found:
        for i, e in enumerate(data["independent"]):
            if e["name"] == plan_name:
                data["independent"].pop(i)
                found = True
                break

    if found:
        _rebuild_plan_index(lines, data)
        plan_index.write_text("".join(lines), encoding="utf-8")
    return found


def move_to_completed_index(plan_name: str, completion_date: str = ""):
    """Move a plan entry from PLAN.md to PLAN_COMPLETED.md. Uses rebuild approach."""
    env = get_env()
    plan_index = env.plans_dir / "PLAN.md"
    completed_index = env.plans_dir / "PLAN_COMPLETED.md"

    if not completed_index.exists():
        init_index_files()

    if not plan_index.exists():
        warn("PLAN.md 不存在，无法迁移条目")
        return False

    # Extract entry details from PLAN.md before removing
    lines = _read_index_lines(plan_index)
    data = _parse_index_entries(lines)

    entry_type = "FULL"
    entry_summary = ""
    found = False

    for e in data["task_groups"]:
        if e["name"] == plan_name:
            entry_type = e.get("type", "FULL")
            entry_summary = e.get("summary", "")
            found = True
            break
    if not found:
        for e in data["independent"]:
            if e["name"] == plan_name:
                entry_type = e.get("type", "FULL")
                entry_summary = e.get("summary", "")
                found = True
                break

    # Remove from PLAN.md
    _remove_from_plan_index(plan_name)

    # Add to PLAN_COMPLETED.md
    if not completion_date:
        from datetime import datetime
        completion_date = datetime.now().strftime("%Y-%m-%d")

    clines = _read_index_lines(completed_index)
    if clines:
        insert_at = _find_table_insert_point(clines, "", r"完成日期.*计划名.*类型.*摘要")
        if insert_at < 0:
            # Fallback: find first separator row, stop at placeholder for replacement
            for i, line in enumerate(clines):
                if re.match(r"^\|[-:| ]+\|$", line.strip()):
                    insert_at = i + 1
                    break

        if insert_at >= 0:
            new_row = f"| {completion_date} | {plan_name} | {entry_type} | {entry_summary} |\n"
            # Replace placeholder if present, otherwise insert
            if insert_at < len(clines) and _PLACEHOLDER_REGEX.match(clines[insert_at].strip()):
                clines[insert_at] = new_row
            else:
                clines.insert(insert_at, new_row)
            completed_index.write_text("".join(clines), encoding="utf-8")
            info(f"已迁移到 PLAN_COMPLETED.md: {plan_name}")
        else:
            warn("无法确定 PLAN_COMPLETED.md 中的插入位置")
            return False

    return True


def _read_index_entries(path: Path) -> list[dict]:
    """Parse a Markdown index file into structured entries."""
    entries = []
    if not path.exists():
        return entries

    lines = _read_index_lines(path)
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|-"):
            continue
        if stripped.startswith("| 序号") or stripped.startswith("| 计划名") or \
           stripped.startswith("| 完成日期"):
            continue
        if _PLACEHOLDER_REGEX.match(stripped):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # Remove leading/trailing empty strings from split, but keep intermediate ones
        # split("|") on "| a | b | c |" gives ['', ' a ', ' b ', ' c ', '']
        # We want ['a', 'b', 'c']
        cells = [c for c in cells if c]
        if cells:
            entries.append({"cells": cells, "raw": stripped})

    return entries


def search_plan_index(keyword: str) -> list[dict]:
    """Search PLAN.md and PLAN_COMPLETED.md for entries matching keyword.

    Returns list of dicts with: source, name, summary, type, extra (status/date).
    """
    env = get_env()
    results = []
    kw = keyword.lower()

    # Search PLAN.md
    plan_index = env.plans_dir / "PLAN.md"
    if plan_index.exists():
        lines = _read_index_lines(plan_index)
        data = _parse_index_entries(lines)
        for e in data["task_groups"]:
            if kw in e["name"].lower() or kw in e["summary"].lower():
                results.append({
                    "source": "PLAN.md",
                    "name": e["name"],
                    "type": e["type"],
                    "summary": e["summary"],
                    "extra": e.get("status", ""),
                })
        for e in data["independent"]:
            if kw in e["name"].lower() or kw in e["summary"].lower():
                results.append({
                    "source": "PLAN.md",
                    "name": e["name"],
                    "type": e["type"],
                    "summary": e["summary"],
                    "extra": e.get("status", ""),
                })

    # Search PLAN_COMPLETED.md
    completed_index = env.plans_dir / "PLAN_COMPLETED.md"
    if completed_index.exists():
        entries = _read_index_entries(completed_index)
        for e in entries:
            cells = e["cells"]
            date = cells[0] if len(cells) > 0 else ""
            name = cells[1] if len(cells) > 1 else ""
            ptype = cells[2] if len(cells) > 2 else ""
            summary = cells[3] if len(cells) > 3 else ""

            if kw in name.lower() or kw in summary.lower():
                results.append({
                    "source": "PLAN_COMPLETED.md",
                    "name": name,
                    "type": ptype,
                    "summary": summary,
                    "extra": date
                })

    return results
