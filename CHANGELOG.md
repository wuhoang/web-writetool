# CHANGELOG

本文件记录每次有意义的变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [1.0.0] - 2026-08-27

POC-2 最终版本。30/30 字段验证通过，5 种布局/策略兼容性测试全部通过。

### Added
- POC-2：Windows UI Automation 网页填写验证
  - `poc/ui_automation.py`：UIA 定位 + pyautogui 写入核心模块（支持 by_id / by_name / by_label 三种定位策略）
  - `poc/run_poc2.py`：POC-2 端到端编排
  - `poc/test_page.html`：模拟填写页面（div 布局）
  - `poc/test_enterprise.html`：企业管理系统仿真（导航栏+侧边栏+Tab）
  - `poc/test_dense_table.html`：仿纸质密集表格
  - `poc/test_vertical.html`：垂直布局（标签在上方）
  - `poc/test_no_id.html`：无 id 属性测试页（仅 name）
  - `config/ui_mapping.yaml`：字段→控件映射配置（by_id 策略）
  - `config/ui_mapping_no_id.yaml`：字段→控件映射配置（by_label 策略）
- 依赖：`pywinauto>=0.6.8`、`pyautogui>=0.9`、`pyperclip>=1.8`

### Fixed
- **Chrome UIA 不支持写入**：改用 pyautogui 坐标点击 + 剪贴板粘贴
- **表格单元格定位失败**：HTML 加 `id` 属性，YAML 改 `by_id`
- **textarea 回读拿到终端文本**：`SetForegroundWindow` 强制前台 + 滚动到屏幕上半区
- **点击落在任务栏**：`_click` 限制 y < screen_h - 50
- **下拉框选错选项**：`option_index` 漏算空白默认项（index 0 = "-- 请选择 --"）
- **页面滚动过慢**：自适应步长（±15/±5/±2），30 次内完成

### Removed
- JS 注入模式（`javascript:` URI）：Chrome 地址栏过滤该前缀，无法执行
- Selenium 方案：需 `--remote-debugging-port` 重启浏览器，真实用户无法接受

## [0.2.0] - 2026-08-26

### Fixed
- **固控设备表串列 bug**：`split_content_by_sections` 的 token 归属逻辑导致钻井液性能表底行数据（含水量/含油量/MBT/氯根）串入固控设备节区。新增 `not_excluded_by_xband` 排除函数，当 token 落在某个有 xband 的节区范围内时，排除掉所有 xband 不包含它的节区。
- **run_poc1.py 未传布局约束**：`main()` 中调用 `parse_document` 时未传入 `boundaries` 和 `xbands`，导致 `document_structure.json` 中间产物与 `business_model.json` 最终产物不一致。现已统一传入布局提示。
- **run_poc1.py print 编码错误**：Windows GBK 终端无法输出特殊字符（如 `³`），改用 `sys.stdout.buffer.write` 兜底。
- **钻井液性能表单位丢失**：`map_fluid_properties` 中 `unit_col` 条件判断错误导致 `None`，性能参数单位未写入输出。简化为 `len(header) > 1` 判断。
- **field_rules.yaml 重复 alias**：`solids_control_table.columns.hours` 中 `"时间,h"` 重复出现，删除多余项。

### Changed
- 修复后固控设备表：3 列带（设备名称/筛布/时间），6 行纯净数据（原 9 列含 4 行脏数据）
- 修复后钻井液性能表：#1~#4 四个取样点全部正确恢复（原 document_structure.json 中 #3/#4 为空）

## [0.1.0] - 2026-08-26

### Added
- POC-1 初始实现：PDF 结构恢复与字段映射
  - `layout_recovery.py`：词提取→视觉行聚类→节区分配→列谷检测→Table/KV/Paragraph
  - `field_mapping.py`：结构→Business Data Model（含溯源与校验）
  - `run_poc1.py`：端到端编排 + 验证报告生成
  - `config/field_rules.yaml`：字段别名/类型/数值范围/布局提示
- 辅助调试工具：explore_pdf.py / inspect_region.py / inspect_fonts.py / debug_assign.py / check_model.py
- 顶层设计文档 v1.3
