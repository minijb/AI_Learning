"""Learning plan shared utilities — plan.md / progress.md parsing."""

import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.theme import Theme

# ── Rich theme ──────────────────────────────────────────────
_LEARN_THEME = Theme({
    "learn.name": "bold cyan",
    "learn.type": "italic dim",
    "learn.goal": "white",
    "learn.status.done": "bold green",
    "learn.status.progress": "bold yellow",
    "learn.status.pending": "dim",
    "learn.status.blocked": "bold red",
    "highlight": "bold white",
    "muted": "dim",
    "warn": "yellow",
    "error": "bold red",
    "info": "cyan",
    "success": "green",
    "progress.bar.complete": "green",
    "progress.bar.incomplete": "dim",
})

_console: Optional[Console] = None


def get_console() -> Console:
    global _console
    if _console is None:
        # Ensure UTF-8 output on Windows
        if sys.platform == "win32":
            for stream in (sys.stdout, sys.stderr):
                if hasattr(stream, "reconfigure"):
                    try:
                        stream.reconfigure(encoding="utf-8")
                    except Exception:
                        pass
        _console = Console(
            theme=_LEARN_THEME,
            highlight=False,
            force_terminal=True,
            legacy_windows=False,
        )
    return _console


# ── Paths ──────────────────────────────────────────────────
class LearningEnv:
    def __init__(self):
        self.workspace = Path(__file__).resolve().parents[4]
        self.docs_dir = self.workspace / "docs"
        self.learning_plans_dir = self.docs_dir / "learning-plans"
        self.active_dir = self.learning_plans_dir / "active"
        self.completed_dir = self.learning_plans_dir / "completed"
        self.index_path = self.learning_plans_dir / "INDEX.md"


def get_env() -> LearningEnv:
    return LearningEnv()


# ── File helpers ───────────────────────────────────────────
def read_file_safe(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


# ── plan.md parsing ────────────────────────────────────────
def parse_plan_md(content: str) -> dict:
    """Parse plan.md into structured data.

    Returns:
        {
            "goal_lines": list[str],        # 学习目标 bullet items
            "prereq_checklist": list[dict], # [{"text": ..., "done": bool}]
            "topics": list[dict],           # [{"seq": str, "name": str, "hours": str, "type": str, "dep": str}]
            "milestones": list[dict],       # [{"text": ..., "done": bool}]
        }
    """
    result = {
        "goal_lines": [],
        "prereq_checklist": [],
        "topics": [],
        "milestones": [],
    }

    # ── Learning goals (## 学习目标) ──
    goal_section = _extract_section(content, "学习目标")
    if goal_section:
        for line in goal_section.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                result["goal_lines"].append(stripped[2:].strip())

    # ── Prerequisites (## 前置要求) ──
    prereq_section = _extract_section(content, "前置要求")
    if prereq_section:
        for line in prereq_section.splitlines():
            stripped = line.strip()
            m = re.match(r"- \[([ x])\] (.+)", stripped)
            if m:
                result["prereq_checklist"].append({
                    "text": m.group(2).strip(),
                    "done": m.group(1) == "x",
                })

    # ── Learning path table (## 学习路径) ──
    path_section = _extract_section(content, "学习路径")
    if path_section:
        in_table = False
        for line in path_section.splitlines():
            stripped = line.strip()
            if "|---" in stripped or "|------" in stripped:
                in_table = True
                continue
            if in_table and stripped.startswith("|") and not stripped.startswith("| 序号"):
                cells = [c.strip() for c in stripped.split("|")]
                cells = [c for c in cells if c]  # remove empty first/last from split
                if len(cells) >= 2:
                    result["topics"].append({
                        "seq": cells[0] if len(cells) > 0 else "",
                        "name": cells[1] if len(cells) > 1 else "",
                        "hours": cells[2] if len(cells) > 2 else "",
                        "type": cells[3] if len(cells) > 3 else "",
                        "dep": cells[4] if len(cells) > 4 else "",
                    })

    # ── Milestones (## 里程碑) ──
    ms_section = _extract_section(content, "里程碑")
    if ms_section:
        for line in ms_section.splitlines():
            stripped = line.strip()
            m = re.match(r"- \[([ x])\] (.+)", stripped)
            if m:
                result["milestones"].append({
                    "text": m.group(2).strip(),
                    "done": m.group(1) == "x",
                })

    return result


# ── progress.md parsing ─────────────────────────────────────
def parse_progress_md(content: str) -> dict:
    """Parse progress.md and compute progress statistics.

    Handles two formats:
      - Table format: | 序号 | 知识点 | 状态 |  with ⬜/✅/🔄
      - Checkbox format: - [x] / - [ ] under section headers

    Returns:
        {
            "topic_total": int,
            "topic_done": int,
            "milestone_total": int,
            "milestone_done": int,
            "blocked": int,           # topics with 🔄 (in-progress/blocked)
        }
    """
    result = {
        "topic_total": 0,
        "topic_done": 0,
        "milestone_total": 0,
        "milestone_done": 0,
        "blocked": 0,
    }

    # Detect format: table-based or checkbox-based
    has_table = "|" in content and ("⬜" in content or "✅" in content)
    has_checkbox = "- [" in content

    if has_table:
        _parse_table_progress(content, result)
    elif has_checkbox:
        _parse_checkbox_progress(content, result)

    return result


def _parse_table_progress(content: str, result: dict):
    """Parse table-format progress.md (game-engine-dev style)."""
    in_table = False
    for line in content.splitlines():
        stripped = line.strip()
        if "|---" in stripped or "|------" in stripped:
            in_table = True
            continue
        if in_table and stripped.startswith("|") and not stripped.startswith("| 序号"):
            result["topic_total"] += 1
            if "✅" in stripped:
                result["topic_done"] += 1
            elif "🔄" in stripped:
                result["blocked"] += 1
            # ⬜ = pending, no action needed


def _parse_checkbox_progress(content: str, result: dict):
    """Parse checkbox-format progress.md (oh-my-pi style).

    Sections are separated by ## headers. Milestone section is identified by
    containing "里程碑" in its header.
    """
    current_section = ""
    for line in content.splitlines():
        stripped = line.strip()

        # Track section
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            continue

        # Parse checkboxes
        m = re.match(r"- \[([ x])\] (.+)", stripped)
        if not m:
            continue

        is_done = m.group(1) == "x"

        if "里程碑" in current_section:
            result["milestone_total"] += 1
            if is_done:
                result["milestone_done"] += 1
        else:
            result["topic_total"] += 1
            if is_done:
                result["topic_done"] += 1


# ── Section extraction ─────────────────────────────────────
def _extract_section(content: str, section_name: str) -> Optional[str]:
    """Extract the content of a ## section by name."""
    pattern = rf"^##\s+[^\n]*{re.escape(section_name)}[^\n]*\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


# ── Progress bar render ────────────────────────────────────
def render_progress_bar(done: int, total: int, width: int = 10) -> str:
    """Render a Rich-markup progress bar string."""
    if total == 0:
        return f"[progress.bar.incomplete]{'░' * width}[/progress.bar.incomplete]"
    filled = done * width // total
    bar = (
        f"[progress.bar.complete]{'█' * filled}[/progress.bar.complete]"
        f"[progress.bar.incomplete]{'░' * (width - filled)}[/progress.bar.incomplete]"
    )
    return bar


# ── Plan.md top-level metadata ─────────────────────────────
def extract_title(content: str) -> str:
    """Extract title from plan.md's first heading."""
    m = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    if m:
        return m.group(1).strip().removeprefix("学习计划:").strip()
    return "未命名计划"


def extract_meta(content: str, key: str) -> str:
    """Extract a metadata field from the frontmatter-style block (e.g. `> 创建日期: ...`)."""
    pattern = rf">\s*{re.escape(key)}[：:]\s*(.+)"
    m = re.search(pattern, content)
    if m:
        return m.group(1).strip()
    return "—"
