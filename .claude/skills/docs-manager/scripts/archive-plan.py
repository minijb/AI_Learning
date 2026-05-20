#!/usr/bin/env python3
"""Archive a completed learning plan from active/ to completed/.

Usage:
    python archive-plan.py <plan-name>
    python archive-plan.py --list-active
"""
import os
import sys
import shutil


DOCS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'docs'))
ACTIVE_DIR = os.path.join(DOCS_ROOT, 'learning-plans', 'active')
COMPLETED_DIR = os.path.join(DOCS_ROOT, 'learning-plans', 'completed')


def list_active():
    if not os.path.isdir(ACTIVE_DIR):
        print('活跃计划目录不存在。')
        return []
    plans = [d for d in os.listdir(ACTIVE_DIR) if os.path.isdir(os.path.join(ACTIVE_DIR, d))]
    if plans:
        print('活跃学习计划:')
        for p in sorted(plans):
            print(f'  - {p}')
    else:
        print('暂无活跃学习计划。')
    return plans


def archive_plan(name):
    src = os.path.join(ACTIVE_DIR, name)
    dst = os.path.join(COMPLETED_DIR, name)

    if not os.path.isdir(src):
        print(f'[ERROR] 未找到活跃计划: {name}')
        sys.exit(1)

    if os.path.exists(dst):
        print(f'[ERROR] 已完成目录已存在同名计划: {name}')
        print('请手动处理冲突后重试。')
        sys.exit(1)

    os.makedirs(COMPLETED_DIR, exist_ok=True)
    shutil.move(src, dst)
    print(f'[OK] 已归档: {name}')
    print(f'     {src} → {dst}')


def main():
    if len(sys.argv) < 2:
        print('Usage: python archive-plan.py <plan-name>')
        print('       python archive-plan.py --list-active')
        sys.exit(1)

    if sys.argv[1] == '--list-active':
        list_active()
    else:
        archive_plan(sys.argv[1])


if __name__ == '__main__':
    main()
