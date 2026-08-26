# 开发现状

> 最后更新：2026-08-26

## 当前版本：POC-1 v0.2.0

### 已完成

#### POC-1：PDF 结构恢复与字段映射 ✅

用 `report_data.pdf`（真实钻井液日报，3 页）验证了完整链路：

```
PDF → PyMuPDF 提取词坐标 → 行聚类 → 节区分配 → 列谷检测 → Table/KV/Paragraph → Business Data Model
```

**核心指标**：
- meta 字段 17/17 命中（井号、日期、测深/垂深、钻井液类型等，含 FSR 派生）
- 钻井液性能表：4 取样点 × 27 参数（密度/粘度/AV/PV/YP/切力/API失水/氯根…）
- 当日材料表：9 行（材料代号/单位/数量）
- 固控设备表：6 行（设备/筛布/时间）
- 长文本段落：2 段原文保真（跨行自动拼接）

**关键技术点**：
1. 表单式 KV 布局：冒号后缀识别 + 同行向右小间隙吸附
2. 多标题同行（并排面板）：容差分组（±3pt）+ 配置化 x 边界
3. 内容归属算法：最近上方标题 + xband 排除（修复了串列 bug）
4. 列检测：x 方向占用直方图找空白谷（≥5pt）
5. 原文保真：段落仅做去折行拼接，不做字符级改写

### 已修复的 Bug（v0.2.0）

| Bug | 根因 | 修复 |
|-----|------|------|
| 固控设备表串入性能表数据 | `split_content_by_sections` 的 token 归属未考虑 xband 排除 | 新增 `not_excluded_by_xband` 函数 |
| document_structure.json 与 business_model.json 不一致 | `run_poc1.py` 调用 `parse_document` 未传布局约束 | 统一传入 boundaries + xbands |
| Windows print 中文编码错误 | GBK 终端无法输出特殊字符 | 改用 sys.stdout.buffer.write 兜底 |
| _section_json 重复调用 | 报告生成阶段对同一节区调用 3 次 | 复用 structure_out 结果 |

### 已知限制（POC 边界内）

1. **版面提示绑定当前模板**：`section_xbands` / `same_row_boundaries` 中的 x 数值绑定 report_data.pdf 的版面，换模板需重配
2. **非 MVP 区域存在噪声**：页1 中部小面板（循环数据/钻具组合/井数据等）之间有少量串列，未影响 MVP 字段
3. **span 粘连风险**：PDF 内部标签和值排进同一 span 时无法拆分
4. **置信度为占位规则**：exact=0.99 / numeric=0.97 / derive=0.9，待实测确定

### 未开始

| 阶段 | 内容 | 状态 |
|------|------|------|
| POC-2 | Windows UI Automation 网页填写验证 | 未开始 |
| MVP-GUI | tkinter 界面（PDF 预览 + 字段核对） | 未开始 |
| MVP-填写 | Locator + Actor 网页自动填写 | 未开始 |
| MVP-打包 | PyInstaller 打包为 exe | 未开始 |

## 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-08-26 | 电子 PDF 走纯几何恢复，不引入 OCR | 文字层坐标足够，OCR 增加复杂度无收益 |
| 2026-08-26 | 配置外挂 YAML | 换模板改配置不改代码，符合 §4.4 原则 |
| 2026-08-26 | 置信度占位，不写死阈值 | 设计文档 §11.2 要求按实测确定 |
| 2026-08-26 | xband 作为硬约束排除 | 修复串列 bug，保证并排面板的水平隔离 |
