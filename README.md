# 钻井液日报智能自动填写工具

从钻井液日报 PDF 中自动提取业务数据，通过 Windows UI Automation 填写到现有业务系统。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# POC-1：PDF 结构恢复验证
python poc/run_poc1.py

# POC-2：网页自动填写验证（需 Chrome）
python poc/run_poc2.py

# 抽查业务模型
python poc/check_model.py
```

POC-2 运行前需确保 Chrome 已安装，脚本会自动启动 Chrome 并填写模拟页面。

## 输出文件

| 文件 | 说明 |
|------|------|
| `poc/output/document_structure.json` | PDF 中间结构（节区/表头/数据行/列带） |
| `poc/output/business_model.json` | 业务数据模型（meta/性能表/材料/固控/段落） |
| `poc/output/poc1_report.txt` | POC-1 验证报告 |
| `poc/output/poc2_report.txt` | POC-2 填写报告（30 字段逐条结果） |

## 项目结构

```
config/
  field_rules.yaml           PDF 字段映射规则
  ui_mapping.yaml            网页控件映射（by_id 策略）
  ui_mapping_no_id.yaml      网页控件映射（by_label 策略，无 id 页面）
docs/顶层设计文档.md          产品顶层设计 v1.3
poc/
  layout_recovery.py         PDF 版面结构恢复
  field_mapping.py           业务字段映射
  run_poc1.py                POC-1 端到端编排
  ui_automation.py           UIA 定位 + pyautogui 写入
  run_poc2.py                POC-2 端到端编排
  test_page.html             测试页面（div 布局）
  test_enterprise.html       测试页面（企业管理系统）
  test_dense_table.html      测试页面（密集表格）
  test_vertical.html         测试页面（垂直布局）
  test_no_id.html            测试页面（无 id 属性）
  check_model.py             业务模型抽查
```

## 验证结果

### POC-1：PDF 结构恢复

| 指标 | 结果 |
|------|------|
| meta 字段 | 17/17 命中（含 FSR 派生） |
| 钻井液性能表 | 4 取样点 × 27 参数全部恢复 |
| 当日材料表 | 9 行全部恢复 |
| 固控设备表 | 6 行全部恢复 |
| 长文本段落 | 2 段原文保真提取 |

### POC-2：网页自动填写

30/30 字段填写成功，5 种布局全部通过：

| 测试页面 | 布局风格 | 定位策略 | 结果 |
|---------|---------|---------|------|
| test_page.html | div 布局 | by_id | 30/30 ✅ |
| test_enterprise.html | 企业管理系统 | by_id | 30/30 ✅ |
| test_dense_table.html | 密集表格 | by_id | 30/30 ✅ |
| test_vertical.html | 垂直布局 | by_id | 30/30 ✅ |
| test_no_id.html | 无 id 属性 | by_label | 30/30 ✅ |

## 技术栈

- Python 3.12+
- PyMuPDF — PDF 文本层提取
- pywinauto — Windows UI Automation 控件定位
- pyautogui + pyperclip — 坐标点击 + 剪贴板粘贴
- PyYAML — 配置解析

## 技术路线

- 电子 PDF：PyMuPDF 提取文字坐标 → 几何关系恢复表格结构（无 OCR）
- 网页填写：UIA 定位控件 → pyautogui 坐标点击 + 剪贴板粘贴
- 配置化：字段映射外挂 YAML，换模板/换系统改配置不改代码
- 溯源：每个字段携带 raw_text + 页码 + bbox + 置信度
