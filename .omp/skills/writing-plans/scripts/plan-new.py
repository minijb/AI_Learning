#!/usr/bin/env python3
"""
plan-new.py — 创建新执行计划
用法: python plan-new.py --quick '计划名称'
       python plan-new.py --full '计划名称'
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    add_to_plan_index, copy_plan_template, error_exit, get_env, info,
    init_index_files, sanitize_name, get_console,
)
from rich.tree import Tree
from rich.panel import Panel
from rich.text import Text


def main():
    parser = argparse.ArgumentParser(description="创建新执行计划")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quick", action="store_true", help="创建轻量计划（≤5 步，单文件改动）")
    group.add_argument("--full", action="store_true", help="创建完整执行计划（跨模块改动，含功能列表）")
    parser.add_argument("name", help="计划名称")
    parser.add_argument("--summary", default="", help="一句话摘要（用于 PLAN.md 索引）")
    parser.add_argument("--depends", default="", help="依赖计划名（多个用逗号分隔，用于任务组）")
    args = parser.parse_args()

    env = get_env()
    console = get_console()
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_name = sanitize_name(args.name)

    init_index_files()
    tech_debt_file = env.plans_dir / "tech-debt-tracker.md"
    if not tech_debt_file.exists():
        tech_debt_file.write_text(
            "# 技术债务追踪\n\n"
            "> 记录计划执行过程中发现的技术债务，计划完成时一并评估。\n\n"
            "| ID | 描述 | 发现日期 | 关联计划 | 优先级 | 状态 |\n"
            "|----|------|---------|---------|--------|------|\n"
            "| TD-001 | [示例] 旧版 API 未加版本号 | - | - | 中 | 待处理 |\n",
            encoding="utf-8",
        )
        info("已创建 docs/exec-plans/tech-debt-tracker.md")

    if args.quick:
        plan_file = env.active_dir / f"{safe_name}.md"
        if plan_file.exists():
            error_exit(f"计划已存在: {plan_file}", "使用不同名称，或先归档旧计划")

        copy_plan_template("quick-plan.md", plan_file)
        content = plan_file.read_text(encoding="utf-8")
        content = content.replace("[一行描述]", args.name)
        content = content.replace("[日期]", date_str)
        plan_file.write_text(content, encoding="utf-8")

        console.print(f"[success]✓[/success] 轻量计划已创建: [plan.name]{plan_file.name}[/plan.name]")

        plan_type = "QUICK"
        summary = args.summary if args.summary else args.name
        add_to_plan_index(safe_name, plan_type, summary, args.depends)

        console.print()
        console.print("[highlight]下一步:[/highlight]")
        console.print("  编辑计划文件，填充验收标准和步骤")
    else:
        plan_dir = env.active_dir / safe_name
        if plan_dir.exists():
            error_exit(f"计划目录已存在: {plan_dir}", "使用不同名称，或先归档旧计划")
        plan_dir.mkdir(parents=True)

        copy_plan_template("exec-plan.md", plan_dir / "exec-plan.md")
        copy_plan_template("feature-list.json", plan_dir / "feature-list.json")
        copy_plan_template("memory.md", plan_dir / "memory.md")

        exec_plan = plan_dir / "exec-plan.md"
        exec_plan.write_text(
            exec_plan.read_text(encoding="utf-8")
            .replace("[计划名称]", args.name)
            .replace("[日期]", date_str),
            encoding="utf-8",
        )

        memory = plan_dir / "memory.md"
        memory.write_text(
            memory.read_text(encoding="utf-8").replace("[计划名称]", args.name),
            encoding="utf-8",
        )

        progress = plan_dir / "progress.txt"
        progress.write_text(
            f"# Progress: {args.name}\n"
            f"# 创建于: {date_str}\n\n"
            f"状态: IN_PROGRESS\n"
            f"最后更新: {date_str}\n\n"
            f"步骤进度:\n"
            f"- [ ] Step 1 — [待填写]\n"
            f"- [ ] Step 2 — [待填写]\n"
            f"- [ ] Step 3 — [待填写]\n\n"
            f"阻塞项: 无\n",
            encoding="utf-8",
        )

        console.print(f"[success]✓[/success] 完整执行计划已创建: [plan.name]{plan_dir.name}/[/plan.name]")

        # File tree
        tree = Tree("", style="muted")
        tree.add("[bold]exec-plan.md[/bold]     填充技术方案和步骤")
        tree.add("[bold]feature-list.json[/bold] 定义功能点，只允许修改 passes")
        tree.add("[bold]memory.md[/bold]        记录关键工件和决策")
        tree.add("[bold]progress.txt[/bold]     执行时更新进度")
        console.print(Panel(tree, title="创建的文件", title_align="left", border_style="muted"))
        console.print()

        plan_type = "FULL"
        summary = args.summary if args.summary else args.name
        add_to_plan_index(safe_name, plan_type, summary, args.depends)

        console.print("[highlight]下一步:[/highlight]")
        console.print("  1. 编辑 [bold]exec-plan.md[/bold] 填充具体方案")
        console.print("  2. 编辑 [bold]feature-list.json[/bold] 定义功能点")
        console.print(f"  3. 运行 [bold]plan-validate.py '{safe_name}'[/bold] 验证计划完整性")


if __name__ == "__main__":
    main()
