#!/usr/bin/env python3
"""
plan-complete.py — 标记计划完成并归档（跨平台 Python）
用法: python plan-complete.py '计划名称'
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Windows terminal UTF-8 support
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from common import error, error_exit, get_env, info, move_to_completed_index, read_plan_json, warn


def find_plan(active_dir: Path, plan_name: str) -> Path:
    exact = active_dir / plan_name
    if exact.exists():
        return exact

    # 模糊匹配目录
    matches = [p for p in active_dir.iterdir() if p.is_dir() and p.name.startswith(plan_name)]
    if not matches:
        # 模糊匹配文件
        matches = [p for p in active_dir.iterdir() if p.is_file() and p.name.startswith(plan_name) and p.suffix == ".md"]

    if len(matches) == 0:
        error_exit(f"未找到活跃计划: {plan_name}", "查看所有活跃计划: python plan-status.py")
    if len(matches) > 1:
        error("找到多个匹配计划:")
        for m in matches:
            kind = "[DIR]" if m.is_dir() else "[FILE]"
            print(f"  - {kind} {m.name}")
        error_exit("", "使用更精确的名称。")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="标记计划完成并归档")
    parser.add_argument("name", help="计划名称")
    parser.add_argument("--force", action="store_true", help="跳过未完成确认，强制归档")
    args = parser.parse_args()

    env = get_env()
    plan_path = find_plan(env.active_dir, args.name)
    base_name = plan_path.name
    completed_dir = env.completed_dir
    completed_dir.mkdir(parents=True, exist_ok=True)

    print(f"计划: {base_name}")
    print(f"路径: {plan_path}")
    print(f"目标: {completed_dir / base_name}")
    print()

    today = datetime.now().strftime("%Y-%m-%d")

    if not args.force:
        if plan_path.is_dir():
            feature_file = plan_path / "feature-list.json"
            if feature_file.exists():
                data = read_plan_json(feature_file)
                if data:
                    feat_count = len(data.get("features", []))
                    done_count = sum(1 for f in data["features"] if f.get("passes") is True)
                    if done_count < feat_count:
                        warn(f"并非所有功能点都已完成 ({done_count}/{feat_count})")
                        confirm = input("  继续归档? (y/N): ").strip().lower()
                        if confirm != "y":
                            print("已取消。")
                            return

            progress_file = plan_path / "progress.txt"
            if progress_file.exists():
                content = progress_file.read_text(encoding="utf-8")
                content = re.sub(r"状态:.*", "状态: COMPLETED", content)
                content = re.sub(r"最后更新:.*", f"最后更新: {today}", content)
                content += f"\n完成日期: {today}\n"
                progress_file.write_text(content, encoding="utf-8")
        else:
            content = plan_path.read_text(encoding="utf-8")
            if "- [ ]" in content:
                warn("仍有未完成的步骤")
                confirm = input("  继续归档? (y/N): ").strip().lower()
                if confirm != "y":
                    print("已取消。")
                    return
            content = content.replace("| 计划完成 | [待填写]", f"| 计划完成 | {today}")
            plan_path.write_text(content, encoding="utf-8")

    # 执行归档
    dest = completed_dir / base_name
    if dest.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if plan_path.is_file():
            new_name = f"{plan_path.stem}-{timestamp}{plan_path.suffix}"
        else:
            new_name = f"{base_name}-{timestamp}"
        warn(f"已完成目录中已存在同名计划，重命名为: {new_name}")
        dest = completed_dir / new_name

    shutil.move(str(plan_path), str(dest))
    # Cleanup: remove empty directory if shutil.move left residue (e.g. Windows .gitkeep)
    if plan_path.exists():
        try:
            if plan_path.is_dir():
                shutil.rmtree(str(plan_path), ignore_errors=True)
            else:
                plan_path.unlink(missing_ok=True)
        except Exception:
            pass
    info(f"计划已归档到: {dest}")

    # 迁移 INDEX 条目: PLAN.md → PLAN_COMPLETED.md
    base = Path(base_name)
    plan_name = base.stem if base.suffix == ".md" else base.name
    move_to_completed_index(plan_name, today)

    # 生成摘要
    summary_name = f"{Path(base_name).stem}-summary.txt"
    summary_file = completed_dir / summary_name
    try:
        lines = [f"计划: {base_name}", f"完成日期: {today}", f"归档时间: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}", ""]
        if dest.is_dir():
            feature_file = dest / "feature-list.json"
            if feature_file.exists():
                data = read_plan_json(feature_file)
                if data:
                    lines.append("功能点完成情况:")
                    for f in data.get("features", []):
                        mark = "x" if f.get("passes") else " "
                        lines.append(f"  [{mark}] {f['id']}: {f['description']}")
        summary_file.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass  # 摘要生成失败不影响主流程


if __name__ == "__main__":
    main()
