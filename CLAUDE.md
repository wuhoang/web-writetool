# CLAUDE.md — AI 开发指引

## 项目概述

钻井液日报智能自动填写工具。从 PDF 钻井液日报中提取业务数据，通过 Windows UI Automation 自动填写到现有业务系统网页。

**当前阶段**：MVP-GUI v1.2.0 已完成（PDF 全页提取 + tkinter 界面 + UIA 自动填写），正在对接真实业务系统。

## 仓库结构

```
config/
  field_rules.yaml           字段别名/类型/数值范围/布局提示（PDF 模板配置）
  ui_mapping.yaml            字段→网页控件映射配置（UIA 定位 + 下拉框选项）
docs/顶层设计文档.md          产品级顶层设计文档 v1.3
gui/                         MVP-GUI 桌面界面
  __init__.py                包标记
  app.py                     MainApp 主窗口（工具栏 + PDF 预览 + 字段核对 + 状态栏）
  pdf_viewer.py              PDF 渲染画布（PyMuPDF PPM → Canvas，翻页/缩放/高亮）
  field_panel.py             字段面板（Treeview 分组展示 + 双击编辑 + 置信度着色）
  fill_runner.py             填写执行对话框（进度条 + 逐字段状态 + 结果汇总）
  run_app.py                 入口脚本（python -m gui.run_app）
poc/
  layout_recovery.py         词提取→视觉行聚类→节区分配→列谷检测→Table/KV
  field_mapping.py           结构→Business Data Model（含溯源与校验）
  run_poc1.py                POC-1 端到端编排 + 生成验证报告
  ui_automation.py           UIA 定位 + pyautogui 写入核心模块
  run_poc2.py                POC-2 端到端编排（启动 Chrome → 自动填写 → 报告）
  test_page.html             模拟填写页面（input/select/textarea/table）
  check_model.py             业务模型抽查脚本
  explore_pdf.py             原始词坐标转储
  inspect_region.py          区域词坐标检查
  inspect_fonts.py           字体/字号检查
  debug_assign.py            节区分配调试
  output/                    所有生成产物（git 不跟踪）
```

## 技术栈

- Python 3.12+
- PyMuPDF (pymupdf) — PDF 文本层提取（POC-1）
- PyYAML — 配置解析
- pywinauto — Windows UI Automation 控件定位（POC-2）
- pyautogui + pyperclip — 坐标点击 + 剪贴板粘贴（POC-2）
- 无 OCR、无 OpenCV、无 Selenium

## 开发约定

### 代码风格
- 类型注解用 `from __future__ import annotations`
- dataclass 优先于 dict 用于内部数据结构
- 函数/变量命名：snake_case
- 配置值全部外化到 YAML，不硬编码模板相关常量

### 核心设计原则（来自顶层设计文档）
- **原文保真**：自然语言字段禁止语义改写，结构化字段仅允许格式标准化
- **可追溯**：每个业务值携带 raw_text + page + bbox + confidence
- **规则可配置**：字段映射关系用 YAML 配置，换模板改配置不改代码
- **轻量化**：普通办公电脑可运行，不依赖云端
- **非侵入**：不修改目标系统，通过 OS 级 UI Automation 操作

### 运行方式
```bash
pip install -r requirements.txt
start.bat                       # 双击启动 MVP-GUI（推荐，含错误提示）
python -m gui.run_app           # MVP-GUI 桌面界面（命令行）
python poc/run_poc1.py          # POC-1: PDF 提取（命令行）
python poc/check_model.py       # 业务模型抽查
python poc/run_poc2.py          # POC-2: 网页填写（需 Chrome，命令行）
```

### 关键算法
1. **行聚类**（cluster_lines）：基于 y 坐标 overlap 的 token 分组
2. **节区分配**（split_content_by_sections）：最近上方标题 + xband 排除逻辑
3. **列谷检测**（detect_column_bands）：x 方向占用直方图找空白谷（≥5pt）
4. **KV 提取**（extract_key_values）：冒号后缀识别 + 同行向右小间隙吸附
5. **UIA 定位 + pyautogui 写入**：UIA 找控件拿坐标 → 自适应滚动到安全区 → 坐标点击+剪贴板粘贴

### POC-2 架构要点
- Chrome 需 `--force-renderer-accessibility` 暴露网页控件到 UIA 树
- UIA 负责定位（by_id），pyautogui 负责写入和回读
- 自适应滚动：大步 ±15 → 小步 ±2，目标 y=200~600（远离地址栏和任务栏）
- 下拉框：`option_index` + `options` 列表配置化，Home+Down+Enter 精确定位
- 焦点管理：`SetForegroundWindow` 强制浏览器前台，防止终端截获键盘
- DPI 感知：`SetProcessDpiAwareness(1)` 统一 UIA/pyautogui 坐标系（高分屏必须）

### MVP-GUI 架构要点
- `gui/app.py`：主窗口，PanedWindow 左右布局（PDF 预览 + 字段面板）
- `gui/pdf_viewer.py`：PyMuPDF PPM 渲染，翻页/缩放/区域高亮
- `gui/field_panel.py`：Treeview 分组展示 + 双击编辑 + 置信度着色
- `gui/fill_runner.py`：填写对话框，后台线程 + 逐字段进度 + 取消按钮
- 全部3页 PDF 提取：第1页主表、第2页材料追踪、第3页钻井液数量日报
- `_get_center` 返回 None 防护：控件不可见时 per-field 隔离失败，不影响其他字段

### 已知限制
- 布局提示（section_xbands / same_row_boundaries）绑定当前 PDF 模板
- 置信度为占位规则（exact=0.99 / numeric=0.97）
- span 粘连场景未处理（标签和值在同一 span 时无法拆分）
- Chrome 需手动启用无障碍（`--force-renderer-accessibility`），真实用户场景需封装
- 下拉框回读不可靠（Chrome 不暴露选中值）
- 高 DPI 屏幕（如 2560×1600 + 150%）需 SetProcessDpiAwareness(1) 统一坐标系
- UIA 控件 rectangle() 可能返回 None（页面未加载完/控件不可见），已做 per-field 隔离

## MVP 后续计划

- ~~MVP-GUI：tkinter 界面（PDF 预览 + 字段核对）~~ ✅ 已完成
- MVP-填写：接入真实业务系统（进行中 — UIA 控件定位调试）
- MVP-打包：PyInstaller 打包为 exe
