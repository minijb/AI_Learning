#!/usr/bin/env python3
"""
plan-search.py — 搜索 PLAN.md 和 PLAN_COMPLETED.md（跨平台 Python）
用法: python plan-search.py <关键词>
       python plan-search.py --all   （列出所有条目）
"""

import argparse
import sys
from pathlib import Path

# Windows terminal UTF-8 support
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from common import get_env, init_index_files, search_plan_index, warn


def main():
    parser = argparse.ArgumentParser(description="搜索计划索引（PLAN.md + PLAN_COMPLETED.md）")
    parser.add_argument("keyword", nargs="?", default="", help="搜索关键词")
    parser.add_argument("--all", action="store_true", help="列出所有条目")
    args = parser.parse_args()

    init_index_files()

    if args.all:
        keyword = ""
        print("===== 所有计划条目 =====")
    elif args.keyword:
        keyword = args.keyword
        print(f"===== 搜索: \"{keyword}\" =====")
    else:
        parser.print_help()
        return

    results = search_plan_index(keyword if keyword else "")

    if not results:
        print()
        if keyword:
            print(f"未找到匹配 \"{keyword}\" 的计划。")
        else:
            print("索引中暂无计划条目。")
        return

    # Group by source
    plan_entries = [r for r in results if r["source"] == "PLAN.md"]
    completed_entries = [r for r in results if r["source"] == "PLAN_COMPLETED.md"]

    if plan_entries:
        print()
        print("--- PLAN.md（活跃计划）---")
        for r in plan_entries:
            extra = r.get("extra", "")
            if extra:
                print(f"  [{r['type']}] [{extra}] {r['name']} — {r['summary']}")
            else:
                print(f"  [{r['type']}] {r['name']} — {r['summary']}")

    if completed_entries:
        print()
        print("--- PLAN_COMPLETED.md（已完成计划）---")
        for r in completed_entries:
            extra = r.get("extra", "")
            print(f"  [{r['type']}] ({extra}) {r['name']} — {r['summary']}")

    print()
    print(f"共 {len(results)} 条匹配")

    if keyword:
        env = get_env()
        print()
        print("💡 提示: 创建新计划前，建议先运行此命令查看是否有类似计划可复用。")


if __name__ == "__main__":
    main()
