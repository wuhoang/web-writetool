# CLAUDE.md — AI 开发指引

## 项目概述

钻井液日报智能自动填写工具。从 PDF 钻井液日报中提取业务数据，通过 Windows UI Automation 自动填写到现有业务系统网页。

**当前阶段**：POC-1（PDF 结构恢复与字段映射验证）已完成。

## 仓库结构

```
config/field_rules.yaml    字段别名/类型/数值范围/布局提示（模板配置）
docs/顶层设计文档.md        产品级顶层设计文档 v1.3
poc/
  layout_recovery.py       词提取→视觉行聚类→节区分配→列谷检测→Table/KV
  field_mapping.py         结构→Business Data Model（含溯源与校验）
  run_poc1.py              端到端编排 + 生成验证报告
  check_model.py           业务模型抽查脚本
  explore_pdf.py           原始词坐标转储
  inspect_region.py        区域词坐标检查
  inspect_fonts.py         字体/字号检查
  debug_assign.py          节区分配调试
  output/                  所有生成产物（git 不跟踪）
```

## 技术栈

- Python 3.12+
- PyMuPDF (pymupdf) — PDF 文本层提取
- PyYAML — 配置解析
- 无 OCR、无 OpenCV（POC-1 阶段）

## 开发约定

### 代码风格
- 类型注解用 `from __future__ import annotations`
- dataclass 优先于 dict 用于内部数据结构
- 函数/变量命名：snake_case
- 配置值全部外化到 `config/field_rules.yaml`，不硬编码模板相关常量

### 核心设计原则（来自顶层设计文档）
- **原文保真**：自然语言字段禁止语义改写，结构化字段仅允许格式标准化
- **可追溯**：每个业务值携带 raw_text + page + bbox + confidence
- **规则可配置**：字段映射关系用 YAML 配置，换模板改配置不改代码
- **轻量化**：普通办公电脑可运行，不依赖云端

### 运行方式
```bash
pip install -r requirements.txt
python poc/run_poc1.py          # 端到端
python poc/check_model.py       # 抽查
```

### 关键算法
1. **行聚类**（cluster_lines）：基于 y 坐标 overlap 的 token 分组
2. **节区分配**（split_content_by_sections）：最近上方标题 + xband 排除逻辑
3. **列谷检测**（detect_column_bands）：x 方向占用直方图找空白谷（≥5pt）
4. **KV 提取**（extract_key_values）：冒号后缀识别 + 同行向右小间隙吸附

### 已知限制
- 布局提示（section_xbands / same_row_boundaries）绑定当前模板
- 置信度为占位规则（exact=0.99 / numeric=0.97）
- span 粘连场景未处理（标签和值在同一 span 时无法拆分）

## POC 后续计划

- POC-2：Windows UI Automation 网页填写验证
- MVP：GUI (tkinter) + 完整闭环
