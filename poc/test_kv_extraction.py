"""extract_key_values 单元测试。

覆盖：
- 正常冒号结尾（如 "钻机:PL19-9J"）
- 冒号在下一个 token 开头（如 "井号" + ": PL19-9-J47"）
- gap 边界：gap=11 进入分支，gap=12 不进入
- 空值跳过
- 同行多组 KV
- 时间标签排除（如 "08:30"）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from layout_recovery import Line, Token, extract_key_values


def _tok(text: str, x0: float, x1: float, page: int = 1) -> Token:
    return Token(page=page, text=text, x0=x0, y0=10, x1=x1, y1=20)


def _line(*tokens: Token) -> Line:
    ln = Line()
    for t in tokens:
        ln.tokens.append(t)
    return ln


def _labels(pairs) -> list[str]:
    return [p.label for p in pairs]


def _values(pairs) -> list[str]:
    return [p.raw_text for p in pairs]


class TestNormalColon:
    """正常情况：token 以冒号结尾。"""

    def test_simple_kv(self):
        line = _line(_tok("钻机:", 0, 30), _tok("PL19-9J", 32, 60))
        pairs = extract_key_values([line])
        assert _labels(pairs) == ["钻机"]
        assert _values(pairs) == ["PL19-9J"]

    def test_multiple_kv_one_line(self):
        line = _line(
            _tok("钻机:", 0, 30), _tok("PL19-9J", 32, 60),
            _tok("井别:", 100, 130), _tok("生产井", 132, 160),
        )
        pairs = extract_key_values([line])
        assert _labels(pairs) == ["钻机", "井别"]
        assert _values(pairs) == ["PL19-9J", "生产井"]

    def test_fullwidth_colon(self):
        line = _line(_tok("区域：", 0, 30), _tok("渤海海域", 32, 70))
        pairs = extract_key_values([line])
        assert _labels(pairs) == ["区域"]
        assert _values(pairs) == ["渤海海域"]

    def test_time_label_excluded(self):
        """时间格式 "08:30" 不应被识别为 KV 标签。"""
        line = _line(_tok("08:30", 0, 30), _tok("开工", 32, 50))
        pairs = extract_key_values([line])
        assert pairs == []


class TestColonInNextToken:
    """冒号在下一个 token 开头（PyMuPDF 拆分）。"""

    def test_basic_split(self):
        # "井号" (0,30) + ": PL19-9-J47" (31,80)  gap=1
        line = _line(_tok("井号", 0, 30), _tok(": PL19-9-J47", 31, 80))
        pairs = extract_key_values([line])
        assert _labels(pairs) == ["井号"]
        assert _values(pairs) == ["PL19-9-J47"]

    def test_split_with_trailing_values(self):
        # "井号" + ": QHD32-6" + "/ FSR: #1"
        line = _line(
            _tok("井号", 0, 30),
            _tok(": QHD32-6", 31, 70),
            _tok("/", 71, 75),
            _tok("FSR:", 76, 90),  # 正常冒号，应作为下一个 KV
            _tok("#1", 92, 100),
        )
        pairs = extract_key_values([line])
        assert len(pairs) == 2
        assert pairs[0].label == "井号"
        assert "QHD32-6" in pairs[0].raw_text
        assert pairs[1].label == "FSR"

    def test_gap_exactly_11_enters_branch(self):
        """gap=11 < 12，应进入冒号分离分支。"""
        line = _line(_tok("well", 0, 30), _tok(": 123", 41, 60))
        pairs = extract_key_values([line])
        assert _labels(pairs) == ["well"]
        assert _values(pairs) == ["123"]

    def test_gap_exactly_12_skips_branch(self):
        """gap=12 不满足 < 12，"well" 被跳过。"""
        line = _line(_tok("well", 0, 30), _tok(": 123", 42, 60))
        pairs = extract_key_values([line])
        # "well" 不以冒号结尾且 gap >= 12，跳过
        # ": 123" 以冒号开头但不是以冒号结尾（整个 token 不以冒号结尾），也跳过
        assert pairs == []

    def test_split_colon_with_fullwidth(self):
        """全角冒号在下一个 token 开头。"""
        line = _line(_tok("井号", 0, 30), _tok("：ABC12-3", 31, 70))
        pairs = extract_key_values([line])
        assert _labels(pairs) == ["井号"]
        assert _values(pairs) == ["ABC12-3"]


class TestEdgeCases:
    def test_empty_line(self):
        pairs = extract_key_values([Line()])
        assert pairs == []

    def test_no_colon(self):
        line = _line(_tok("没有冒号", 0, 60), _tok("的文本", 62, 90))
        pairs = extract_key_values([line])
        assert pairs == []

    def test_colon_only_no_value(self):
        """标签后没有值，应跳过。"""
        line = _line(_tok("井段:", 0, 30))
        pairs = extract_key_values([line])
        assert pairs == []

    def test_split_colon_no_value_after(self):
        """冒号分离但后面没有值 token，应跳过。"""
        line = _line(_tok("井号", 0, 30), _tok(":", 31, 33))
        pairs = extract_key_values([line])
        assert pairs == []

    def test_value_gap_too_large(self):
        """值 token 与标签间距过大（>15），应跳过。"""
        line = _line(_tok("标签:", 0, 30), _tok("远处的值", 100, 140))
        pairs = extract_key_values([line])
        assert pairs == []
