# 钻井液日报智能自动填写工具

从钻井液日报 PDF 中自动提取业务数据，通过 Windows UI Automation 填写到现有业务系统。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行 POC-1（PDF 结构恢复验证）
python poc/run_poc1.py

# 抽查业务模型
python poc/check_model.py
```

## 输出文件

运行 `run_poc1.py` 后在 `poc/output/` 下生成：

| 文件 | 说明 |
|------|------|
| `document_structure.json` | 中间结构（节区/表头/数据行/列带） |
| `business_model.json` | 业务数据模型（meta/性能表/材料/固控/段落） |
| `poc1_report.txt` | 人读验证报告 |

## 项目结构

```
config/field_rules.yaml    字段映射规则（模板配置）
docs/顶层设计文档.md        产品顶层设计
poc/
  layout_recovery.py       PDF 版面结构恢复
  field_mapping.py         业务字段映射
  run_poc1.py              端到端编排
  check_model.py           业务模型抽查
  explore_pdf.py           PDF 原始数据转储
  inspect_region.py        区域坐标检查
  inspect_fonts.py         字体检查
  debug_assign.py          节区分配调试
```

## POC-1 验证结果

| 指标 | 结果 |
|------|------|
| meta 字段 | 17/17 命中（含 FSR 派生） |
| 钻井液性能表 | 4 取样点 × 27 参数全部恢复 |
| 当日材料表 | 9 行全部恢复 |
| 固控设备表 | 6 行全部恢复（3 列：设备/筛布/时间） |
| 长文本段落 | 2 段原文保真提取 |

## 技术路线

- 电子 PDF：PyMuPDF 提取文字坐标 → 几何关系恢复表格结构（无 OCR、无 OpenCV）
- 配置化：字段映射规则外挂 YAML，换模板改配置不改代码
- 溯源：每个字段携带 raw_text + 页码 + bbox + 置信度

## 后续计划

- POC-2：Windows UI Automation 网页填写验证
- MVP：tkinter GUI + 完整闭环
