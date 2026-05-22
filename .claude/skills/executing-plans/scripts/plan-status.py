#!/usr/bin/env python3
"""
plan-status.py — 查看所有活跃计划的进度（跨平台 Python）
输出格式: grep-friendly，含显式状态标记
"""

import sys
from pathlib import Path

# Windows terminal UTF-8 support
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, get_progress_summary, info


def main():
    env = get_env()
    active_dir = env.active_dir

    if not active_dir.exists():
        print("没有活跃计划。（docs/exec-plans/active/ 目录不存在）")
        print("创建计划: python plan-new.py --full '计划名称'")
        return

    items = [p for p in active_dir.iterdir() if p.name != ".gitkeep"]

    if not items:
        print("没有活跃计划。")
        print("创建计划: python plan-new.py --full '计划名称'")
        return

    print(f"===== 活跃计划 ({len(items)}) =====")
    print()

    total_done = 0
    total_all = 0
    total_blocked = 0

    for item in sorted(items):
        plan_name = item.stem if item.is_file() else item.name

        if item.is_dir():
            type_mark = "[FULL]"
            summary = get_progress_summary(item)
            done_count = summary["done"]
            feat_count = summary["total"]
            blocked = summary["blocked"]

            total_done += done_count
            total_all += feat_count
            total_blocked += blocked

            pct = (done_count * 100 // feat_count) if feat_count else 0

            if blocked > 0:
                status = f"[BLOCKED:{blocked}]"
            elif done_count >= feat_count and feat_count > 0:
                status = "[DONE]"
            else:
                status = "[IN_PROGRESS]"

            print(f"{plan_name:<40} {type_mark} {status}  {done_count}/{feat_count} ({pct}%)")

            # 若存在 tasks/ 目录，统计 Task 文件完成情况
            tasks_dir = item / "tasks"
            if tasks_dir.is_dir():
                task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == '.md'])
                if task_files:
                    task_total = len(task_files)
                    task_done = 0
                    for tf in task_files:
                        tcontent = tf.read_text(encoding="utf-8")
                        all_cb = len(re.findall(r'- \[.\]', tcontent))
                        done_cb = len(re.findall(r'- \[x\]', tcontent))
                        if all_cb > 0 and done_cb >= all_cb:
                            task_done += 1
                    # 用 tasks/ 统计补充显示（不替代 feature-list.json 统计，两者并存）
                    print(f"  Tasks: {task_done}/{task_total} 完成")

        else:
            type_mark = "[QUICK]"
            content = item.read_text(encoding="utf-8")

            import re
            step_total = len(re.findall(r"- \[.\] \*\*Step", content))
            step_done = len(re.findall(r"- \[x\] \*\*Step", content))

            pct = (step_done * 100 // step_total) if step_total else 0

            total_done += step_done
            total_all += step_total

            if "[BLOCKED]" in content:
                status = "[BLOCKED]"
            elif step_done >= step_total and step_total > 0:
                status = "[DONE]"
            else:
                status = "[IN_PROGRESS]"

            print(f"{plan_name:<40} {type_mark} {status}  {step_done}/{step_total} ({pct}%)")

    print()
    print("===== 汇总 =====")
    if total_all > 0:
        overall_pct = total_done * 100 // total_all
        print(f"总进度: {total_done}/{total_all} ({overall_pct}%)")
    else:
        print("总进度: 0/0 (0%)")
    print(f"阻塞项: {total_blocked}")
    print(f"活跃计划: {len(items)}")


if __name__ == "__main__":
    main()
