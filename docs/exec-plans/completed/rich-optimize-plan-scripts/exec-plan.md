# Rich 优化 Plan 相关 Python 脚本

**Goal:** 使用 Rich 库美化所有 plan 相关 CLI 脚本的输出，消除手动的 box-drawing、padding 计算、裸 print。

**Architecture:** 
- 共享 Console + Theme 定义在 `_planning_common.py`
- 所有脚本复用同一 Console 实例
- 替换 info/warn/error/error_exit 为 Rich 样式输出
- 表格用 `rich.table.Table`
- 卡片用 `rich.panel.Panel`
- 进度条用 Rich 内建 BarColumn 风格
- 文件树用 `rich.tree.Tree`

**Tech Stack:** Python 3.11+, Rich 15.0.0

## Task 1: 升级 `_planning_common.py` — 共享 Rich Console 和样式
- 定义 Theme（info: dim cyan, warning: yellow, danger: bold red, success: green）
- 创建全局 Console 实例 `get_console()`
- 重写 info/warn/error/error_exit 使用 Rich 样式
- 添加 `_read_file_safe()` 到共享库（消除各脚本重复定义）
- 添加 `_extract_goal()` 到共享库
- 消除 Windows UTF-8 设置代码（Rich 自动处理）

## Task 2: 重写 `plan-status.py` — 表格化输出
- 使用 `rich.table.Table` 替代固定列宽的 print 格式
- 进度百分比用彩色文本
- 汇总行用 Panel 包裹

## Task 3: 重写 `plan-active.py` — Panel 卡片
- 使用 `rich.panel.Panel` 替代手动 Unicode box-drawing
- 进度条用 Rich renderable bar
- 任务状态用 Tree 展示

## Task 4: 重写 `plan-detail.py` — 分区 Panel
- 概览/功能点/任务进度/阻塞项/文件清单 各用 Panel 包裹
- 功能点表格用 Table
- 文件清单用 Tree

## Task 5: 重写 `plan-completed.py` — Panel 卡片
- 同 plan-active.py 模式，使用 Panel 卡片

## Task 6: 重写 `plan-complete.py` — 样式化流程输出
- info/warn 自动获 Rich 样式（通过 _planning_common.py 升级生效）

## Task 7: 重写 `plan-cleanup.py` — 表格化清理预览
- 清理预览用 Table 展示
- info/warn 自动获 Rich 样式

## Task 8: 重写 `plan-validate.py` — 分区错误输出
- 错误/警告分组用 Panel
- 通过 _planning_common.py 升级自动获 Rich 样式

## Task 9: 重写 `plan-search.py` — 表格化搜索结果
- 使用 Table 替代手动格式化的 print

## Task 10: 重写 `plan-new.py` — 样式化创建确认
- info 输出自动获 Rich 样式
- 文件清单用 Tree

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Rich API 版本差异导致输出样式不一致 | 低 | 中 | 锁定 Rich >=13.0，所有脚本复用同一 Console 实例；验证时对比各脚本输出一致性 |
| 管道/重定向时 ANSI 码未正确降级 | 中 | 高 | Rich Console 默认 `force_terminal=False` 可自动检测；验证时显式测试管道输出 |
| 手动 box-drawing 代码遗漏未清理 | 中 | 低 | 验证步骤中加入 `search` 扫描 Unicode box-drawing 字符（╭╰├─） |
| 共享库改动导致未修改脚本报错 | 中 | 高 | Task 1 完成时即跑全量脚本回归，后续每 Task 跑一次；保持向后兼容 |
| Windows 终端编码问题（Rich v13 前已知） | 低 | 低 | 要求 Rich >=13.0；验证在 Windows Terminal 下执行 |

## 验收标准
- [x] 所有脚本可正常运行，输出无 ANSI 乱码
- [x] 管道/重定向时自动降级为纯文本
- [x] plan-status.py 输出结构化表格
- [x] plan-active.py 输出 Rich Panel 卡片
- [x] plan-detail.py 输出分区 Panel
- [x] plan-completed.py 输出 Rich Panel 卡片
- [x] 各脚本不再有手动 box-drawing 代码
- [x] 各脚本不再有手动 UTF-8 设置代码
