"""Layout recovery: PDF tokens -> lines -> sections -> tables / key-values / paragraphs.

Implements the geometric path described in the design doc section 4.2/4.3:
electronic PDF text layer only, no OCR, no OpenCV. Structure is recovered
from word coordinates (line clustering, column valleys, bold-title anchors).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

BOLD_MARKER = "Bold"
COLON_CHARS = ":："



@dataclass
class Token:
    page: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    bold: bool = False

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Line:
    tokens: list[Token] = field(default_factory=list)

    def add(self, token: Token) -> None:
        self.tokens.append(token)
        self.tokens.sort(key=lambda t: t.x0)

    @property
    def page(self) -> int:
        return self.tokens[0].page

    @property
    def y0(self) -> float:
        return min(t.y0 for t in self.tokens)

    @property
    def y1(self) -> float:
        return max(t.y1 for t in self.tokens)

    @property
    def x0(self) -> float:
        return min(t.x0 for t in self.tokens)

    @property
    def x1(self) -> float:
        return max(t.x1 for t in self.tokens)

    def text(self, gap: float = 1.2) -> str:
        out = ""
        prev: Token | None = None
        for t in self.tokens:
            if prev is not None and t.x0 - prev.x1 > gap * max(prev.height, 1):
                out += " "
            out += t.text
            prev = t
        return out.strip()

    def all_bold(self) -> bool:
        return bool(self.tokens) and all(t.bold for t in self.tokens)


@dataclass
class Section:
    title: str
    page: int
    title_bbox: tuple[float, float, float, float]
    tokens: list[Token] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)


@dataclass
class KeyValue:
    label: str
    value_tokens: list[Token]
    page: int

    @property
    def raw_text(self) -> str:
        return " ".join(t.text for t in self.value_tokens).strip()

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (
            min(t.x0 for t in self.value_tokens),
            min(t.y0 for t in self.value_tokens),
            max(t.x1 for t in self.value_tokens),
            max(t.y1 for t in self.value_tokens),
        )


def extract_page_lines(page: pymupdf.Page, page_no: int) -> list[Line]:
    tokens: list[Token] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"]
                if not text.strip():
                    continue
                font = span["font"]
                if len(text.strip()) == 1 and text.strip() in COLON_CHARS and tokens:
                    last = tokens[-1]
                    if span["bbox"][0] - last.x1 < 2.5:
                        last.text += text.strip()
                        last.x1 = span["bbox"][2]
                        last.bold = last.bold or BOLD_MARKER in font
                        continue
                tokens.append(
                    Token(
                        page=page_no,
                        text=text.strip(),
                        x0=span["bbox"][0],
                        y0=span["bbox"][1],
                        x1=span["bbox"][2],
                        y1=span["bbox"][3],
                        bold=BOLD_MARKER in font,
                    )
                )
    return cluster_lines(tokens)


def cluster_lines(tokens: list[Token]) -> list[Line]:
    lines: list[Line] = []
    for token in sorted(tokens, key=lambda t: (t.y0, t.x0)):
        target: Line | None = None
        for line in reversed(lines):
            overlap_top = max(token.y0, line.y0)
            overlap_bottom = min(token.y1, line.y1)
            overlap = overlap_bottom - overlap_top
            if overlap > 0.5 * min(token.height, line.y1 - line.y0):
                target = line
                break
        if target is None:
            target = Line()
            lines.append(target)
        target.add(token)
    lines.sort(key=lambda ln: ln.y0)
    return lines


def find_title_tokens(lines: list[Line], titles: set[str]) -> list[tuple[Token, str]]:
    normalized = {t.replace(" ", ""): t for t in titles}
    found: list[tuple[Token, str]] = []
    for line in lines:
        for token in line.tokens:
            if not token.bold:
                continue
            key = token.text.replace(" ", "")
            if key in normalized:
                found.append((token, normalized[key]))
    found.sort(key=lambda pair: (pair[0].y0, pair[0].x0))
    return found


def split_content_by_sections(
    lines: list[Line],
    title_pairs: list[tuple[Token, str]],
    boundaries: dict[str, float] | None = None,
    xbands: dict[str, tuple[float, float]] | None = None,
) -> tuple[list[Section], list[Line]]:
    """Assign every content token to the nearest section title ABOVE it.

    When xbands are configured, a token is excluded from any section whose
    xband does NOT contain the token's cx — even if that section is closer
    vertically.  This prevents tokens from one table's horizontal domain
    bleeding into a neighbouring table below it.

    Optional template hints (config-driven):
      xbands     - hard horizontal range per section title
      boundaries - x cut between two same-row titles ("A|B" -> x)
    """
    boundaries = boundaries or {}
    xbands = xbands or {}
    sections: list[Section] = []
    title_token_ids = {id(tk) for tk, _ in title_pairs}
    for token, title in title_pairs:
        sections.append(Section(title=title, page=token.page, title_bbox=(token.x0, token.y0, token.x1, token.y1)))

    # Pre-compute: which page-level xbands exist (for exclusion logic)
    page_xbands: dict[int, list[tuple[float, float]]] = {}
    for idx, (_, title) in enumerate(title_pairs):
        band = xbands.get(title)
        if band is not None:
            page_xbands.setdefault(title_pairs[idx][0].page, []).append(band)

    def band_ok(idx: int, token: Token) -> bool:
        band = xbands.get(title_pairs[idx][1])
        return band is None or band[0] <= token.cx <= band[1]

    def not_excluded_by_xband(idx: int, token: Token) -> bool:
        """Return False if the token's cx is inside a DIFFERENT section's
        xband on the same page but NOT inside this section's xband.
        This prevents cross-table bleed when two tables are side-by-side."""
        my_band = xbands.get(title_pairs[idx][1])
        if my_band is not None:
            # This section has an xband – the normal band_ok check suffices.
            return my_band[0] <= token.cx <= my_band[1]
        # This section has no xband.  Check if the token belongs to another
        # section's xband on the same page (only check sections that DO have
        # an xband, to avoid excluding sections that legitimately own tokens
        # in the shared horizontal space).
        for other_idx in by_page.get(token.page, []):
            other_band = xbands.get(title_pairs[other_idx][1])
            if other_band is not None and other_band[0] <= token.cx <= other_band[1]:
                return False  # token is inside another section's xband
        return True  # no xband claims this token – allow y-based assignment

    by_page: dict[int, list[int]] = {}
    for idx, (tk, _) in enumerate(title_pairs):
        by_page.setdefault(tk.page, []).append(idx)

    def resolve_same_row(cands: list[int], cx: float) -> int:
        if len(cands) == 1:
            return cands[0]
        ordered = sorted(cands, key=lambda idx: title_pairs[idx][0].x0)
        for a_idx, b_idx in zip(ordered, ordered[1:]):
            ta, tb = title_pairs[a_idx][0], title_pairs[b_idx][0]
            name_a, name_b = title_pairs[a_idx][1], title_pairs[b_idx][1]
            key = f"{name_a}|{name_b}"
            if key in boundaries:
                bnd = boundaries[key]
            else:
                bnd = (ta.x1 + tb.x0) / 2
            if cx < bnd:
                return a_idx
        return ordered[-1]

    header_tokens: list[Token] = []
    for line in lines:
        for token in line.tokens:
            if id(token) in title_token_ids:
                continue
            ups = [
                idx for idx in by_page.get(line.page, [])
                if token.y0 >= title_pairs[idx][0].y0 - 3
                and band_ok(idx, token)
                and not_excluded_by_xband(idx, token)
            ]
            if not ups:
                header_tokens.append(token)
                continue
            owner = -1
            for level_y in sorted({title_pairs[idx][0].y0 for idx in ups}, reverse=True):
                group = [idx for idx in ups if abs(title_pairs[idx][0].y0 - level_y) <= 3]
                eligible = [
                    idx for idx in group
                    if not (abs(token.y0 - title_pairs[idx][0].y0) < 4
                            and token.cx < title_pairs[idx][0].x0)
                ]
                if not eligible:
                    continue
                owner = resolve_same_row(eligible, token.cx)
                break
            if owner < 0:
                header_tokens.append(token)
            else:
                sections[owner].tokens.append(token)

    for sec in sections:
        sec.lines = cluster_lines(sec.tokens)
        sec.tokens = []

    header_lines = cluster_lines(header_tokens)
    header_lines.sort(key=lambda ln: (ln.page, ln.y0))
    return sections, header_lines


def _same_line(a: Line, b: Line) -> bool:
    overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
    return overlap > 0.5 * min(a.y1 - a.y0, b.y1 - b.y0)


def detect_column_bands(
    section_lines: list[Line], min_gap_pt: float = 5.0, scale: int = 2
) -> list[tuple[float, float]]:
    """Find vertical whitespace valleys across all rows -> column bands."""
    occupied: set[int] = set()
    for line in section_lines:
        for t in line.tokens:
            b0 = int(t.x0 * scale)
            b1 = int(t.x1 * scale)
            occupied.update(range(b0, max(b0 + 1, b1)))
    if not occupied:
        return []
    lo, hi = min(occupied), max(occupied)
    left_edge = lo / scale - 2
    right_edge = (hi + 1) / scale + 2

    boundaries = [left_edge]
    run_start: int | None = None
    for b in range(lo, hi + 1):
        if b not in occupied:
            if run_start is None:
                run_start = b
        else:
            if run_start is not None:
                if (b - run_start) / scale >= min_gap_pt:
                    boundaries.append((run_start + b) / 2 / scale)
                run_start = None

    boundaries.append(right_edge)
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def line_to_cells(line: Line, bands: list[tuple[float, float]]) -> list[str]:
    cells = [""] * len(bands)
    for token in line.tokens:
        best_idx, best_dist = 0, 10**9
        for i, (b0, b1) in enumerate(bands):
            dist = 0 if b0 <= token.cx <= b1 else min(abs(token.cx - b0), abs(token.cx - b1))
            if dist < best_dist:
                best_idx, best_dist = i, dist
        sep = "" if not cells[best_idx] else " "
        cells[best_idx] += (sep if cells[best_idx] else "") + token.text
    return [c.strip() for c in cells]


def extract_table(section: Section) -> dict:
    bands = detect_column_bands(section.lines)
    rows: list[list[str]] = []
    header_rows: list[int] = []
    for i, line in enumerate(section.lines):
        rows.append(line_to_cells(line, bands))
        if line.all_bold():
            header_rows.append(i)
    first_header = header_rows[0] if header_rows else 0
    header = rows[first_header] if header_rows else [f"col{i}" for i in range(len(bands))]
    data = [r for i, r in enumerate(rows) if i not in set(header_rows)]
    return {
        "bands": bands,
        "header": header,
        "data": data,
        "all_rows": rows,
        "header_row_indexes": header_rows,
        "first_header_index": first_header,
    }


TIME_LABEL_RE = re.compile(r"^\d{1,2}[:：]\d{2}")


def extract_key_values(lines: list[Line]) -> list[KeyValue]:
    pairs: list[KeyValue] = []
    for line in lines:
        tokens = line.tokens
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if not token.text.endswith(tuple(COLON_CHARS)) or TIME_LABEL_RE.match(token.text):
                i += 1
                continue
            label = token.text.rstrip(COLON_CHARS).strip()
            values: list[Token] = []
            j = i + 1
            while j < len(tokens):
                nxt = tokens[j]
                if nxt.text.endswith(tuple(COLON_CHARS)):
                    break
                if values and nxt.x0 - values[-1].x1 > 12:
                    break
                if not values and nxt.x0 - token.x1 > 15:
                    break
                values.append(nxt)
                j += 1
            if label and values:
                pairs.append(KeyValue(label=label, value_tokens=values, page=token.page))
                i = j
            else:
                i += 1
    return pairs


def parse_document(
    pdf_path: Path,
    section_titles: set[str],
    boundaries: dict[str, float] | None = None,
    xbands: dict[str, tuple[float, float]] | None = None,
) -> dict:
    doc = pymupdf.open(pdf_path)
    result = {"pages": [], "sections": [], "header_kv": []}
    all_header_lines: list[Line] = []
    for pno, page in enumerate(doc):
        lines = extract_page_lines(page, pno + 1)
        result["pages"].append({"page": pno + 1, "width": page.rect.width, "height": page.rect.height, "line_count": len(lines)})
        title_pairs = find_title_tokens(lines, section_titles)
        sections, header_lines = split_content_by_sections(lines, title_pairs, boundaries, xbands)
        result["sections"].extend(sections)
        all_header_lines.extend(header_lines)
    result["header_kv"] = extract_key_values(all_header_lines)
    return result
