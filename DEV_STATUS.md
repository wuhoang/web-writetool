# 开发现状

> 最后更新：2026-08-27

## 当前版本：MVP-GUI v1.2.0

### 已完成

#### 全页提取：第2、3页数据纳入 ✅

将 PDF 3 页数据全部纳入提取范围（原仅提取第1页）。

**新增提取**：
| 页 | 节区 | 字段数 |
|---|------|--------|
| 2 | 材料追踪 | 费用汇总(6行) + 27 种材料消耗明细 |
| 3 | 钻井液数量日报 | 6 个罐 + 井筒泥浆(3行) + 钻井液平衡(11行) |

**改动**：
- `config/field_rules.yaml`：新增 `section_titles` + `material_tracking` + `fluid_volume_report` 配置
- `poc/field_mapping.py`：新增 `map_material_tracking()` + `map_fluid_volume_report()` 映射函数
- `gui/field_panel.py`：新增"材料追踪 (第2页)"和"钻井液数量 (第3页)"展示分组

#### MVP-GUI：tkinter 桌面界面 ✅

将 POC-1（PDF 提取）和 POC-2（网页填写）串联为完整工作流的桌面 GUI。

**功能**：
- PDF 预览（PyMuPDF 渲染，翻页/缩放/高亮定位）
- 字段核对（Treeview 分组展示，置信度着色，双击编辑）
- 一键填写（连接浏览器 + 自动填写 + 进度展示）

**工作流**：
```
选择PDF → 自动解析 → 人工核对/编辑 → 连接浏览器 → 一键填写 → 查看结果
```

**运行方式**：`python -m gui.run_app`

**新增文件**：

| 文件 | 说明 |
|------|------|
| `gui/__init__.py` | 包标记 |
| `gui/app.py` | MainApp 主窗口（~230 行） |
| `gui/pdf_viewer.py` | PDF 渲染画布（~170 行） |
| `gui/field_panel.py` | 字段面板 + 编辑（~230 行） |
| `gui/fill_runner.py` | 填写进度对话框（~130 行） |
| `gui/run_app.py` | 入口脚本（~20 行） |

**技术要点**：
- PDF 渲染用 PPM 格式（tkinter 原生支持，无 PIL 依赖）
- 填写在子线程执行，`root.after()` 安全更新 GUI
- 不修改任何 POC 模块，纯新增层

#### POC-2：Windows UI Automation 网页填写验证 ✅

用模拟页面 `test_page.html` + POC-1 产出的 `business_model.json` 验证完整填写链路。

**验证结果**：30/30 字段填写成功
| 类型 | 数量 | 回读验证 |
|------|------|---------|
| 文本输入框 | 17 | ✅ 剪贴板回读一致 |
| 下拉选择框 | 3 | ✅ 页面确认选中正确 |
| 表格单元格 | 11 | ✅ 剪贴板回读一致 |
| 多行文本框 | 2 | ✅ 剪贴板回读一致（原文保真） |

**多布局兼容性测试**（2026-08-27）：

| 测试页面 | 布局风格 | 定位策略 | 结果 |
|---------|---------|---------|------|
| `test_page.html` | div 布局（原始） | by_id | 30/30 ✅ |
| `test_enterprise.html` | 企业管理系统（导航栏+侧边栏+Tab+卡片） | by_id | 30/30 ✅ |
| `test_dense_table.html` | 仿纸质密集表格（纯 table） | by_id | 30/30 ✅ |
| `test_vertical.html` | 垂直布局（标签在上方） | by_id | 30/30 ✅ |
| `test_no_id.html` | 无 id 属性（仅 name） | by_label | 30/30 ✅ |

`by_id` 适用于有 HTML id 的页面（最常见），`by_label` 适用于无 id 的旧系统（通过标签文本推断相邻控件）。

**技术架构**：UIA 定位 + pyautogui 写入

```
配置 (ui_mapping.yaml)
  ↓
UIA 定位控件 (pywinauto, by_id)
  ↓
判断控件是否在可视区域 → 不在则自适应滚动
  ↓
填写 (pyautogui click + 剪贴板粘贴 / Home+Down+Enter)
  ↓
回读验证 (Ctrl+A/C → 剪贴板比对)
```

**新增文件**：

| 文件 | 说明 |
|------|------|
| `poc/ui_automation.py` | UIA 定位 + pyautogui 写入核心模块 |
| `poc/run_poc2.py` | POC-2 端到端编排 |
| `poc/test_page.html` | 模拟填写页面（input/select/textarea/table） |
| `config/ui_mapping.yaml` | 字段→控件映射配置（含 option_index） |

**性能**：
- 页面顶部字段：~550ms/字段
- 需滚动字段：~4s/字段
- 多行文本框（需大幅滚动）：~10s/字段
- 30 字段总计约 55 秒

#### POC-1：PDF 结构恢复与字段映射 ✅

用 `report_data.pdf`（真实钻井液日报，3 页）验证完整链路。

**验证结果**：meta 17/17 命中，4 张子表全部提取成功。

### 已修复的 Bug

#### POC-2

| Bug | 根因 | 修复 |
|-----|------|------|
| Chrome UIA 不支持写入 | `set_edit_text()`/`type_keys()` 对 web 元素无效 | 改用 pyautogui 坐标点击+剪贴板粘贴 |
| 表格单元格定位失败 | HTML `<input>` 缺 `id` 属性 | HTML 加 `id`，YAML 改 `by_id` |
| textarea 回读拿到终端文本 | 滚动后浏览器丢失焦点 | `SetForegroundWindow` + 滚动到屏幕上半区 |
| 点击落在任务栏 | textarea 坐标靠近屏幕底部 | `_click` 限制 y < screen_h - 50 |
| 下拉框选错选项 | `option_index` 漏算空白默认项 | 修正 index（空白项占 index 0） |
| 页面滚动过慢 | 每次 5 格，60 次循环 | 自适应步长（±15/±5/±2），30 次内完成 |

#### POC-1

| Bug | 根因 | 修复 |
|-----|------|------|
| 固控设备表串入性能表数据 | token 归属未考虑 xband 排除 | 新增 `not_excluded_by_xband` |
| document_structure 与 business_model 不一致 | `parse_document` 未传布局约束 | 统一传入 |
| Windows print 编码错误 | GBK 终端输出特殊字符 | `sys.stdout.buffer.write` 兜底 |
| 性能表单位丢失 | `unit_col` 条件判断错误 | 简化为 `len(header) > 1` |
| field_rules.yaml 重复 alias | "时间,h" 重复 | 删除多余项 |

### 已知限制

1. **Chrome 需启用无障碍**：`--force-renderer-accessibility` 启动参数
2. **浏览器必须在前台**：pyautogui 是全局键盘/鼠标模拟，不能后台运行
3. **下拉框回读不可靠**：Chrome `<select>` 不暴露选中值到剪贴板
4. **版面/坐标绑定当前模板**：PDF 布局提示、UIA 控件 ID 绑定当前模板
5. **置信度为占位规则**：exact=0.99 / numeric=0.97 / derive=0.9

### 未开始

| 阶段 | 内容 | 状态 |
|------|------|------|
| MVP-填写 | 接入真实业务系统 | 未开始 |
| MVP-打包 | PyInstaller 打包为 exe | 未开始 |

## 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-08-27 | 删除 JS 注入模式 | Chrome 地址栏过滤 `javascript:` 前缀，无法执行 |
| 2026-08-27 | 放弃 Selenium 方案 | 需 `--remote-debugging-port` 重启浏览器，真实用户无法接受 |
| 2026-08-27 | 下拉框用 option_index 配置化 | index 最快最可靠，配置化后换系统只改 YAML |
| 2026-08-27 | UIA 定位 + pyautogui 写入混合架构 | Chrome UIA 只读不写；pyautogui 通用但需前台 |
| 2026-08-26 | 电子 PDF 走纯几何恢复 | 文字层坐标足够 |
| 2026-08-26 | 配置外挂 YAML | 换模板改配置不改代码 |
| 2026-08-26 | xband 作为硬约束排除 | 修复串列 bug |
