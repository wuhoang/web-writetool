# CHANGELOG

本文件记录每次有意义的变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [0.2.0] - 2026-08-26

### Fixed
- **固控设备表串列 bug**：`split_content_by_sections` 的 token 归属逻辑导致钻井液性能表底行数据（含水量/含油量/MBT/氯根）串入固控设备节区。新增 `not_excluded_by_xband` 排除函数，当 token 落在某个有 xband 的节区范围内时，排除掉所有 xband 不包含它的节区。
- **run_poc1.py 未传布局约束**：`main()` 中调用 `parse_document` 时未传入 `boundaries` 和 `xbands`，导致 `document_structure.json` 中间产物与 `business_model.json` 最终产物不一致。现已统一传入布局提示。
- **run_poc1.py print 编码错误**：Windows GBK 终端无法输出特殊字符（如 `³`），改用 `sys.stdout.buffer.write` 兜底。
- **_section_json 重复调用**：报告生成阶段对同一节区调用 3 次 `_section_json`（含 detect_column_bands + extract_table），改为复用 `structure_out` 中的结果。

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
