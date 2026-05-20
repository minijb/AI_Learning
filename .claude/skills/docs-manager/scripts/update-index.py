#!/usr/bin/env python3
"""Update INDEX.md files in the docs system.

Usage:
    python update-index.py learning-plans
    python update-index.py knowledge-notes
    python update-index.py deep-dives
    python update-index.py --all
"""
import os
import sys
from datetime import date


DOCS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'docs'))


def update_learning_plans_index():
    """Scan active/ and completed/ dirs, rebuild INDEX.md."""
    active_dir = os.path.join(DOCS_ROOT, 'learning-plans', 'active')
    completed_dir = os.path.join(DOCS_ROOT, 'learning-plans', 'completed')
    index_path = os.path.join(DOCS_ROOT, 'learning-plans', 'INDEX.md')

    active_plans = []
    if os.path.isdir(active_dir):
        for name in sorted(os.listdir(active_dir)):
            plan_dir = os.path.join(active_dir, name)
            if os.path.isdir(plan_dir):
                plan_md = os.path.join(plan_dir, 'plan.md')
                if os.path.isfile(plan_md):
                    active_plans.append(name)

    completed_plans = []
    if os.path.isdir(completed_dir):
        for name in sorted(os.listdir(completed_dir)):
            plan_dir = os.path.join(completed_dir, name)
            if os.path.isdir(plan_dir):
                completed_plans.append(name)

    lines = [
        '# 学习计划索引',
        '',
        f'> 自动生成于 {date.today().isoformat()}',
        '',
        '## 进行中',
        '',
    ]
    if active_plans:
        lines.append('| 计划名称 | 创建日期 |')
        lines.append('|---------|---------|')
        for name in active_plans:
            lines.append(f'| {name} | — |')
    else:
        lines.append('暂无进行中的学习计划。')
    lines.append('')

    lines.append('## 已完成')
    lines.append('')
    if completed_plans:
        lines.append('| 计划名称 | 完成日期 |')
        lines.append('|---------|---------|')
        for name in completed_plans:
            lines.append(f'| {name} | — |')
    else:
        lines.append('暂无已完成的学习计划。')
    lines.append('')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[OK] 已更新: {index_path}')


def update_knowledge_notes_index():
    """Scan knowledge-notes/ dir, rebuild INDEX.md."""
    notes_dir = os.path.join(DOCS_ROOT, 'knowledge-notes')
    index_path = os.path.join(notes_dir, 'INDEX.md')

    categories = {}
    if os.path.isdir(notes_dir):
        for item in sorted(os.listdir(notes_dir)):
            item_path = os.path.join(notes_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                md_files = [f for f in os.listdir(item_path) if f.endswith('.md') and f != 'INDEX.md']
                if md_files:
                    categories[item] = sorted(md_files)

    lines = [
        '# 知识笔记索引',
        '',
        f'> 自动生成于 {date.today().isoformat()}',
        '',
    ]
    if categories:
        for cat, files in sorted(categories.items()):
            lines.append(f'## {cat}')
            lines.append('')
            for f in files:
                name = f.replace('.md', '')
                lines.append(f'- [{name}]({cat}/{f})')
            lines.append('')
    else:
        lines.append('暂无知识笔记。')
        lines.append('')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[OK] 已更新: {index_path}')


def update_deep_dives_index():
    """Scan deep-dives/ dir, rebuild INDEX.md."""
    dives_dir = os.path.join(DOCS_ROOT, 'deep-dives')
    index_path = os.path.join(dives_dir, 'INDEX.md')

    md_files = []
    if os.path.isdir(dives_dir):
        for item in sorted(os.listdir(dives_dir)):
            if item.endswith('.md') and item != 'INDEX.md':
                md_files.append(item)

    lines = [
        '# 深度探索索引',
        '',
        f'> 自动生成于 {date.today().isoformat()}',
        '',
    ]
    if md_files:
        for f in md_files:
            name = f.replace('.md', '')
            lines.append(f'- [{name}]({f})')
    else:
        lines.append('暂无深度探索记录。')
    lines.append('')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[OK] 已更新: {index_path}')


def main():
    if len(sys.argv) < 2:
        print('Usage: python update-index.py <learning-plans|knowledge-notes|deep-dives|--all>')
        sys.exit(1)

    target = sys.argv[1]
    if target in ('learning-plans', '--all'):
        update_learning_plans_index()
    if target in ('knowledge-notes', '--all'):
        update_knowledge_notes_index()
    if target in ('deep-dives', '--all'):
        update_deep_dives_index()


if __name__ == '__main__':
    main()
