#!/usr/bin/env python3
"""
plan-validate.py — 验证计划完整性（跨平台 Python）
原则: 成功沉默，失败输出含修复指令
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Windows terminal UTF-8 support
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from common import error, error_exit, get_env, info, read_plan_json, warn


ERROR_COUNT = 0
WARN_COUNT = 0


def add_error(msg: str, fix: str = ""):
    global ERROR_COUNT
    error(msg, fix)
    ERROR_COUNT += 1


def add_warn(msg: str):
    global WARN_COUNT
    warn(msg)
    WARN_COUNT += 1


PLACEHOLDER_PATTERNS = [
    (r'\bTBD\b', 'TBD'),
    (r'\bTODO\b', 'TODO'),
    (r'\bFIXME\b', 'FIXME'),
    (r'implement\s+later', 'implement later'),
    (r'fill\s+in\s+details', 'fill in details'),
    (r'add\s+appropriate\s+error\s+handling', 'add appropriate error handling'),
    (r'handle\s+edge\s+cases', 'handle edge cases（除非列出具体 case 和处理方式）'),
    (r'write\s+tests?\s+for\s+the\s+above', 'write tests for the above'),
    (r'similar\s+to\s+Task\s+\d+', 'similar to Task N'),
]

# feature-list.json 模板默认值，不应视为占位符错误
_FEATURE_TEMPLATE_DEFAULTS = {
    "[功能描述 — 人类定义]",
    "[子步骤 1]", "[子步骤 2]", "[子步骤 3]", "[子步骤 4]",
}


def _has_forbidden_placeholder(text: str) -> str | None:
    """检查文本中是否包含禁止占位符（排除模板默认值）。返回违规标签或 None。"""
    if not text:
        return None
    # 先替换模板默认值
    for tmpl in _FEATURE_TEMPLATE_DEFAULTS:
        text = text.replace(tmpl, "")
    # 再检查禁止模式
    for pattern, label in PLACEHOLDER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def check_no_placeholders(content: str, source: str):
    """检查计划中是否包含禁止的占位符模式。跳过 pattern 文档行。"""
    for pattern, label in PLACEHOLDER_PATTERNS:
        for line in content.split('\n'):
            # 跳过文档 pattern 的行（如 "TBD/TODO/..." 这种列表）
            if re.search(r'`?TBD`?\s*[/,]\s*`?TODO`?', line):
                continue
            matches = re.findall(pattern, line, re.IGNORECASE)
            for match in matches:
                add_error(
                    f"{source} 含禁止占位符: '{match}'（模式: {label}）",
                    "零占位符原则：计划中不能有未定义的模糊描述。用具体代码/命令替换。"
                )


def validate_quick_plan(plan_path: Path):
    info(f"验证轻量计划: {plan_path}")
    content = plan_path.read_text(encoding="utf-8")

    for section in ("## 目标", "## 验收标准", "## 影响文件", "## 步骤", "## 回滚方案"):
        if section not in content:
            add_error(f"缺少必填节: {section}", f"在计划中添加 '{section}' 节。")

    if not re.search(r"- \[.\]", content):
        add_error("验收标准为空或格式不正确", "使用 '- [ ] 具体条件' 格式添加至少一条验收标准。")

    step_count = len(re.findall(r"- \[.\] \*\*Step", content))
    if step_count == 0:
        add_error("未找到步骤（格式: '- [ ] **Step N**'）", "按模板格式添加至少一个步骤。")
    elif step_count > 5:
        add_warn(f"步骤数 ({step_count}) 超过 5 步，建议使用完整执行计划（--full 模式）。")

    # 零占位符检查
    check_no_placeholders(content, f"{plan_path.name}")


def validate_full_plan(plan_dir: Path):
    info(f"验证完整执行计划: {plan_dir}")

    required_files = ("exec-plan.md", "feature-list.json", "memory.md", "progress.txt")
    for fname in required_files:
        if not (plan_dir / fname).is_file():
            add_error(f"缺少文件: {fname}", "使用技能目录下 templates/ 中的文件补全。")

    # tasks/ 目录为可选——存在时验证结构，不存在不报错
    tasks_dir = plan_dir / "tasks"
    if tasks_dir.is_dir():
        task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == '.md'])
        if not task_files:
            add_warn("tasks/ 目录存在但为空，建议添加 Task 文件或删除空目录")
        else:
            for tf in task_files:
                tcontent = tf.read_text(encoding="utf-8")
                if not re.search(r'# Task\s+\d+:', tcontent):
                    add_error(f"tasks/{tf.name} 缺少 '# Task NN:' 标题", "按 task-template.md 格式添加标题。")
                # 零占位符检查
                check_no_placeholders(tcontent, f"{plan_dir.name}/tasks/{tf.name}")

    exec_plan = plan_dir / "exec-plan.md"
    if exec_plan.exists():
        content = exec_plan.read_text(encoding="utf-8")
        for section in ("## 风险与缓解", "## 验收标准"):
            if section not in content:
                add_error(f"exec-plan.md 缺少必填节: {section}", f"添加 '{section}' 节。")
        if not re.search(r"## Task\s+\d+:", content):
            add_error("exec-plan.md 缺少 Task 节", "添加至少一个 '## Task N:' 节。")

    feature_file = plan_dir / "feature-list.json"
    if feature_file.exists():
        try:
            with open(feature_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            add_error("feature-list.json 不是有效的 JSON", "检查 JSON 语法。")
            data = None

        if data is not None:
            features = data.get("features")
            if features is None:
                add_error("feature-list.json 缺少 'features' 数组", '添加 "features": [...] 字段。')
            elif len(features) == 0:
                add_error("feature-list.json 的 features 数组为空", "至少添加一个功能条目。")
            else:
                for feat in features:
                    fid = feat.get("id")
                    if not fid or fid == "null":
                        add_error("feature 缺少 id 字段", "为每个 feature 添加唯一 'id'（如 F1, F2）。")
                    if not feat.get("category") or feat.get("category") == "null":
                        add_error(f"feature '{fid}' 缺少 category 字段", "添加 'category' 字段。")
                    desc = feat.get("description", "")
                    if not desc or desc == "null":
                        add_error(f"feature '{fid}' 缺少 description 字段", "添加 'description' 字段。")
                    else:
                        bad = _has_forbidden_placeholder(desc)
                        if bad:
                            add_error(
                                f"feature '{fid}' description 含禁止占位符: {bad}",
                                "零占位符原则：用具体描述替换模糊描述。"
                            )
                    steps = feat.get("steps", [])
                    for s in steps:
                        bad = _has_forbidden_placeholder(s)
                        if bad:
                            add_error(
                                f"feature '{fid}' steps 含禁止占位符: {bad}",
                                "零占位符原则：用具体步骤替换模糊描述。"
                            )

                non_false = sum(1 for f in features if f.get("passes") is not False)
                if non_false > 0:
                    add_warn(f"feature-list.json 中 {non_false} 个 feature 的 passes 初始值不是 false。所有 passes 应初始为 false。")

    # 零占位符检查 — 对所有 Markdown 文件
    for check_file in plan_dir.iterdir():
        if check_file.is_file() and check_file.suffix == '.md':
            try:
                file_content = check_file.read_text(encoding="utf-8")
                check_no_placeholders(file_content, f"{plan_dir.name}/{check_file.name}")
            except Exception:
                pass  # 编码问题，跳过

    progress_file = plan_dir / "progress.txt"
    if progress_file.exists():
        content = progress_file.read_text(encoding="utf-8")
        if "状态:" not in content:
            add_error("progress.txt 缺少 '状态:' 字段", "添加 '状态: IN_PROGRESS' 或其他状态。")


def main():
    parser = argparse.ArgumentParser(description="验证计划完整性")
    parser.add_argument("plan_path", help="计划路径（文件或目录）")
    args = parser.parse_args()

    env = get_env()
    plan_path = Path(args.plan_path)

    if not plan_path.exists():
        alt = env.active_dir / args.plan_path
        if alt.exists():
            plan_path = alt
        else:
            add_error(f"计划不存在: {plan_path}", "检查路径是否正确。使用 plan-status.py 查看所有活跃计划。")
            sys.exit(1)

    if plan_path.is_file():
        validate_quick_plan(plan_path)
    elif plan_path.is_dir():
        validate_full_plan(plan_path)
    else:
        add_error(f"无效的计划路径（不是文件也不是目录）: {plan_path}", "计划必须是 .md 文件（轻量）或目录（完整执行计划）。")

    print("---")
    if ERROR_COUNT == 0 and WARN_COUNT == 0:
        pass  # 成功沉默
    elif ERROR_COUNT == 0:
        print(f"[PASS] 验证通过（{WARN_COUNT} 个警告）")
    else:
        print(f"验证失败: {ERROR_COUNT} 个错误, {WARN_COUNT} 个警告")
        sys.exit(1)


if __name__ == "__main__":
    main()
