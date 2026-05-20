#!/usr/bin/env python3
"""搭建学习计划目录骨架。

Usage:
    python scaffold-plan.py <plan-name> [--slug <slug>]
    python scaffold-plan.py --help

根据 templates/ 创建完整的计划目录结构：
    docs/learning-plans/active/<slug>/
    ├── plan.md          ← 从 templates/plan-template.md 复制
    ├── progress.md      ← 空进度文件
    ├── resources.md     ← 空资源文件
    └── tutorials/
        └── INDEX.md     ← 空教程索引

如果 --slug 未指定，自动从 plan-name 生成（英文名/拼音）。
"""
import os
import re
import sys
import shutil
from datetime import date


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.abspath(os.path.join(SKILL_DIR, '..', '..', '..'))
DOCS_ROOT = os.path.join(WORKSPACE, 'docs')
ACTIVE_DIR = os.path.join(DOCS_ROOT, 'learning-plans', 'active')
TEMPLATES_DIR = os.path.join(SKILL_DIR, 'templates')


def slugify(name):
    """将中文名转拼音或保留英文标识符。简化版：移除特殊字符，空格转连字符。"""
    name = name.strip().lower()
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[\s_]+', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')


def scaffold(plan_name, slug=None):
    if slug is None:
        slug = slugify(plan_name)
        if not slug:
            print('[ERROR] 无法从计划名称生成 slug，请用 --slug 手动指定')
            sys.exit(1)

    plan_dir = os.path.join(ACTIVE_DIR, slug)

    if os.path.exists(plan_dir):
        print(f'[ERROR] 计划目录已存在: {plan_dir}')
        sys.exit(1)

    # 创建目录结构
    tutorials_dir = os.path.join(plan_dir, 'tutorials')
    os.makedirs(tutorials_dir, exist_ok=True)

    # 复制 plan.md 模板
    plan_template = os.path.join(TEMPLATES_DIR, 'plan-template.md')
    if os.path.isfile(plan_template):
        shutil.copy(plan_template, os.path.join(plan_dir, 'plan.md'))
    else:
        print(f'[WARN] 未找到模板: {plan_template}，跳过 plan.md')

    # 生成 progress.md
    progress_path = os.path.join(plan_dir, 'progress.md')
    with open(progress_path, 'w', encoding='utf-8') as f:
        f.write(f'# 进度追踪: {plan_name}\n\n')
        f.write(f'> 创建日期: {date.today().isoformat()}\n')
        f.write(f'> 总进度: 0%\n\n')
        f.write('## 学习路径\n\n')
        f.write('| 序号 | 知识点 | 状态 |\n')
        f.write('|------|--------|------|\n')
        f.write('| — | 待添加 | ⬜ |\n')

    # 生成 tutorials/INDEX.md
    index_path = os.path.join(tutorials_dir, 'INDEX.md')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('# 教程索引\n\n')
        f.write('> 教程文件按知识依赖关系排序。\n\n')
        f.write('| 序号 | 知识点 | 文件 |\n')
        f.write('|------|--------|------|\n')
        f.write('| — | 待添加 | — |\n')

    # 生成 resources.md
    resources_path = os.path.join(plan_dir, 'resources.md')
    with open(resources_path, 'w', encoding='utf-8') as f:
        f.write(f'# 学习资源: {plan_name}\n\n')
        f.write('## 官方文档\n\n## 推荐书籍\n\n## 在线教程\n\n## 社区资源\n\n## 开源项目\n')

    print(f'[OK] 学习计划骨架已创建: {plan_dir}')
    print(f'     下一步: 填充 plan.md → 生成教程 → 运行 update-index.py')

    return plan_dir


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    plan_name = sys.argv[1]
    slug = None

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--slug' and i + 1 < len(sys.argv):
            slug = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    scaffold(plan_name, slug)


if __name__ == '__main__':
    main()
