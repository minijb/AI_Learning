# Task [NN]: [组件名称]

> 所属计划: [计划名称] | 执行顺序: 第 [NN] 步

**Files:**
- Create: `exact/path/to/new_file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test_file.py`

- [ ] **Step 1: 写测试**
  ```python
  # [写出具体测试代码]
  def test_specific_behavior():
      result = function_name(input_value)
      assert result == expected_value
  ```
  - 验证：`pytest tests/path/test_file.py::test_specific_behavior -v` → 预期 **FAIL**（功能未实现）

- [ ] **Step 2: 按规格实现**
  - 文件：`exact/path/to/new_file.py`
  - 签名：`def function_name(input_value: str) -> dict:`
  - 行为：接收 X，校验 Y 不为空，调用 Z 获取数据，返回 `{id, name, status}`
  - 关键约束：Y 为空时抛 `ValueError("Y is required")`；Z 超时 3s
  - 验证：`pytest tests/path/test_file.py::test_specific_behavior -v` → 预期 **PASS**
  
  > 配置文件/脚本类 Step 写完整内容。应用代码类 Step 写上述规格——执行者根据规格自主实现。

- [ ] **Step 3: Commit**
  ```bash
  git add tests/path/ src/path/
  git commit -m "feat: [简短描述]"
  ```
  - 验证：`git log -1 --oneline` → 预期：`feat: [简短描述]`
