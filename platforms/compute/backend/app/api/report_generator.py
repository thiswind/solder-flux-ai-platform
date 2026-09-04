"""
云锡助焊剂 AI 预测系统 — PDF 报告生成器（专业版 v17）

支持两种报告类型：
  - prediction: 性能预测报告（蓝色系，已定稿）
  - optimization: 配方优化报告（绿色系对比风格，v12 按用户确认效果图重排）

v12 变更（按用户确认的最终效果图 v3）：
  - 页眉恢复为正确的绿色大标题 + 编号/时间/操作人 + 全宽绿色分隔线
  - 新增「最优参数结果」6 宫格：氧含量/粒度方案、黏度初值(Pa)、Ti、锡粉规格、助焊剂比例、合金含量
    （数据均来自前端已传的 best_result.outputs 与 recommended_params，无需改前端）
  - 预期性能对比去掉括号释义后缀（仅显示原始值）
  - 删除底部免责声明
  - 优化建议保持 2 条（整体建议 + 优化方向）
  - 后端分数尺度自动修正（检测 0~1 分制时 ×10 对齐基准分）
  - green_section 保持轻量风格（粗体+绿色下划线）

v17 修复（合金含量推荐配方无值）：
  - 根因：grid 扫描任务不携带 alloy_content，前端兜底误用不存在的 formX.alloy_content → 传 "NaN" 给后端
  - 前端 ReasoningV3.vue：recommendedParams.alloy_content 兜底改回 alloyContent.value（= 100 - 助焊剂比例）
  - 后端 rval/adj 增加 _is_blank 判定（识别 "NaN" 字符串），无效时回退 base_input
"""

import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── 注册中文字体 ────────────────────────────────────────
try:
    pdfmetrics.registerFont(TTFont("SimHei", "C:/Windows/Fonts/simhei.ttf"))
    pdfmetrics.registerFont(TTFont("SimSun", "C:/Windows/Fonts/simsun.ttc"))
    _FONT = "SimHei"
    _FONT_BODY = "SimSun"
except Exception:
    _FONT = "Helvetica"
    _FONT_BODY = "Helvetica"

# ── 色彩方案 ────────────────────────────────────────────
PRIMARY = colors.HexColor("#165DFF")
PRIMARY_LIGHT = colors.HexColor("#E8F3FF")
ACCENT_GREEN = colors.HexColor("#00B42A")
TEXT_DARK = colors.HexColor("#1D2129")
TEXT_SECONDARY = colors.HexColor("#86909C")
TEXT_LABEL = colors.HexColor("#4E5969")
BORDER = colors.HexColor("#E5E6EB")
TABLE_HEADER_BG = colors.HexColor("#F2F3F5")
TABLE_BOX_BG = colors.HexColor("#F7F8FA")     # 表格独立圆角容器底色
CARD_SHADOW = colors.HexColor("#E3E6EB")      # 卡片微投影色

PAGE_W, PAGE_H = A4

# ── 布局尺寸体系（统一用 pt，避免混乱）─────────────────
# Frame: 左右各 18mm 边距
FRAME_W = PAGE_W - 36 * mm
CARD_PAD = 12          # 卡片内边距 (pt)
BAR_W = 4              # 左侧蓝竖线宽 (pt)
CONTENT_W = FRAME_W - 2 * CARD_PAD - BAR_W        # 卡片内容可用宽
TABLE_PAD = 8          # 表格圆角容器内边距 (pt)
TABLE_W = CONTENT_W - 2 * TABLE_PAD               # 表格实际宽

# ── 分类等级 → 释义映射（仅内部参考，不展示武断"判定"）──
WETTING_MEANING = {"4": "优秀", "3": "良好", "2": "中等", "1": "较差"}
COLLAPSE_MEANING = {"冷": "低风险", "热": "高风险"}
SOLDERBALL_MEANING = {"1": "最优", "2": "良好", "3": "一般", "4": "较差"}


# ════════════════════════════════════════════════════════
#  样式工厂
# ════════════════════════════════════════════════════════

def _style(name="Normal", font=_FONT_BODY, size=10, **kw) -> ParagraphStyle:
    base = getSampleStyleSheet()[name]
    return ParagraphStyle(f"auto_{name}_{size}", parent=base,
                          fontName=font, fontSize=size, **kw)


def _p(text, font=_FONT_BODY, size=10, **kw):
    return Paragraph(text, _style(font=font, size=size, **kw))


def _bold(text, size=11, color=TEXT_DARK):
    return _p(f"<b>{text}</b>", font=_FONT, size=size, textColor=color)


# ════════════════════════════════════════════════════════
#  自定义 Flowable：圆角容器 & 带阴影卡片
# ════════════════════════════════════════════════════════

class RoundedBox(Flowable):
    """浅色圆角背景容器，用于包裹表格，形成独立视觉区块。"""

    def __init__(self, content, width, bg, radius=6, pad_x=8, pad_y=8):
        super().__init__()
        self.content = content
        self.width = width
        self.bg = bg
        self.radius = radius
        self.pad_x = pad_x
        self.pad_y = pad_y
        self._h = 0

    def wrap(self, aw, ah):
        cw, ch = self.content.wrap(self.width - self.pad_x * 2, ah)
        self._h = ch + self.pad_y * 2
        return (self.width, self._h)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self._h, self.radius,
                    fill=1, stroke=0)
        c.restoreState()
        self.content.drawOn(c, self.pad_x, self.pad_y)


class ShadowedCard(Flowable):
    """圆角白卡 + 微投影 + 左侧蓝色竖线标题装饰。"""

    def __init__(self, content, width, pad=CARD_PAD, bar_w=BAR_W):
        super().__init__()
        self.content = content
        self.width = width
        self.pad = pad
        self.bar_w = bar_w
        self._h = 0

    def wrap(self, aw, ah):
        cw, ch = self.content.wrap(
            self.width - self.pad * 2 - self.bar_w, ah)
        self._h = ch + self.pad * 2
        return (self.width, self._h)

    def draw(self):
        c = self.canv
        w, h = self.width, self._h
        c.saveState()
        # 微投影（右下方偏移的浅灰圆角矩形）
        c.setFillColor(CARD_SHADOW)
        c.roundRect(1.5, -1.5, w, h, 8, fill=1, stroke=0)
        # 白卡主体
        c.setFillColor(colors.white)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, w, h, 8, fill=1, stroke=1)
        # 左侧蓝色竖线（顶部一段，作为标题装饰）
        bar_h = min(h * 0.45, 26)
        c.setFillColor(PRIMARY)
        c.roundRect(0, h - 14 - bar_h, self.bar_w, bar_h, 1.5,
                    fill=1, stroke=0)
        c.restoreState()
        # 内容（右移留出蓝竖线空间）
        self.content.drawOn(c, self.pad + self.bar_w, self.pad)


# ════════════════════════════════════════════════════════
#  页眉（大标题 + 编号/时间/操作人 + 彩色分隔线）
# ════════════════════════════════════════════════════════

def _draw_header(canvas, doc, title, report_id="", operator="Admin",
                 title_color=PRIMARY):
    canvas.saveState()

    # ── 大标题（彩色）──
    canvas.setFillColor(title_color)
    canvas.setFont(_FONT, 22)
    canvas.drawString(18 * mm, PAGE_H - 20 * mm, title)

    # ── 副标题行：报告编号 / 生成时间 / 操作人 ──
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    canvas.setFont(_FONT_BODY, 9)
    canvas.setFillColor(TEXT_SECONDARY)
    sub_parts = []
    if report_id:
        sub_parts.append(f"报告编号：{report_id}")
    sub_parts.append(f"生成时间：{now_str}")
    sub_parts.append(f"操作人：{operator}")
    sub_text = "    ".join(sub_parts)
    canvas.drawString(18 * mm, PAGE_H - 30 * mm, sub_text)

    # ── 彩色分隔线（与标题同色）──
    canvas.setStrokeColor(title_color)
    canvas.setLineWidth(1.5)
    canvas.line(18 * mm, PAGE_H - 37 * mm, PAGE_W - 18 * mm, PAGE_H - 37 * mm)

    canvas.restoreState()


def _draw_opt_header(canvas, doc, report_id="", operator="Admin"):
    """优化报告专用页眉：黑色大标题 + 绿色副标题 + 编号行。"""
    canvas.saveState()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 第 1 行：黑色大标题 ──
    canvas.setFillColor(TEXT_DARK)
    canvas.setFont(_FONT, 20)
    canvas.drawString(18 * mm, PAGE_H - 18 * mm,
                      "锡膏配方优化报告重设计方案 — 绿色系对比风格")

    # ── 第 2 行：编号/时间/操作人（右对齐）──
    canvas.setFont(_FONT_BODY, 9)
    canvas.setFillColor(TEXT_SECONDARY)
    info_text = f"报告编号 {report_id}    生成时间 {now_str}    操作人 {operator}"
    # 右对齐到页面右边距
    canvas.drawRightString(PAGE_W - 18 * mm, PAGE_H - 28 * mm, info_text)

    # ── 第 3 行：绿色副标题 + 下划线 ──
    canvas.setFillColor(ACCENT_GREEN)
    canvas.setFont(_FONT, 16)
    canvas.drawString(18 * mm, PAGE_H - 40 * mm, "锡膏配方优化报告")
    # 绿色下划线
    canvas.setStrokeColor(ACCENT_GREEN)
    canvas.setLineWidth(1.8)
    line_y = PAGE_H - 44 * mm
    canvas.line(18 * mm, line_y,
                18 * mm + canvas.stringWidth("锡膏配方优化报告", _FONT, 16),
                line_y)

    canvas.restoreState()


# ════════════════════════════════════════════════════════
#  页脚
# ════════════════════════════════════════════════════════

def _draw_footer(canvas, doc):
    canvas.saveState()
    y = 10 * mm
    canvas.setFont(_FONT_BODY, 8)
    canvas.setFillColor(TEXT_SECONDARY)
    canvas.drawCentredString(PAGE_W / 2, y, f"— {doc.page} —")
    canvas.restoreState()


# ════════════════════════════════════════════════════════
#  卡片容器（核心组件）
# ════════════════════════════════════════════════════════

def card(title_text, content_elements, title_size=12):
    """
    创建一个视觉卡片：
    - 圆角白卡 + 微投影（ShadowedCard）
    - 内部顶部：加粗标题（左侧蓝竖线由卡片外壳绘制）
    - 内部下方：内容元素（表格等，各自带圆角容器）
    """
    rows = [[_bold(title_text, size=title_size)]]
    for elem in content_elements:
        rows.append([elem])

    inner = Table(rows, colWidths=[CONTENT_W])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 5),
        ("LINEBELOW", (0, 0), (0, 0), 0.4, BORDER),
        ("TOPPADDING", (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
    ]))
    return ShadowedCard(inner, width=FRAME_W)


# ════════════════════════════════════════════════════════
#  绿色分区组件（优化报告专用，区别于预测报告的蓝竖线卡片）
# ════════════════════════════════════════════════════════

def green_section(title_text, content_elements, with_line=True):
    """优化报告分区：可选绿线 + 粗体标题 + 内容。"""
    rows = []
    if with_line:
        hdr = _p("", size=2)
        hdr_t = Table([[hdr]], colWidths=[FRAME_W], rowHeights=[2])
        hdr_t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT_GREEN)]))
        rows.append([hdr_t])

    ttl = Paragraph(
        '<font color="%s"><b>%s</b></font>' % (TEXT_DARK.hexval(), title_text),
        _style(font=_FONT, size=12))
    ttl_t = Table([[ttl]], colWidths=[FRAME_W])
    ttl_t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    rows.append([ttl_t])
    for elem in content_elements:
        rows.append([elem])

    sec = Table(rows, colWidths=[FRAME_W])
    sec.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
    ]))
    return sec


def _with_meaning(value, meaning_map):
    """给优化预期值附加括号内的含义说明（沿用预测报告已有的释义映射）。"""
    v = str(value) if value is not None else "-"
    if v in meaning_map:
        return f"{v}（{meaning_map[v]}）"
    return v


class _Capsule(Flowable):
    """胶囊标签：白底 + 绿边 + 绿字 + 完全圆角（用户确认样式）。"""

    def __init__(self, text, max_width=None):
        super().__init__()
        self.text = text
        self.max_width = max_width or 120
        self._h = 0
        self._pad_x = 10
        self._pad_y = 4

    def wrap(self, aw, ah):
        from reportlab.pdfbase import pdfmetrics
        text_w = pdfmetrics.stringWidth(self.text, _FONT, 9)
        self._w = min(text_w + self._pad_x * 2, self.max_width)
        self._h = 22
        return (self._w, self._h)

    def draw(self):
        c = self.canv
        c.saveState()
        r = self._h / 2
        # 白底 + 绿边
        c.setFillColor(colors.white)
        c.setStrokeColor(ACCENT_GREEN)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self._w, self._h, r, fill=1, stroke=1)
        # 绿色文字居中
        c.setFillColor(ACCENT_GREEN)
        c.setFont(_FONT, 9)
        c.drawCentredString(self._w / 2, 5, self.text)
        c.restoreState()


def _pill(text, max_width=120):
    """白底绿字胶囊标签（自动宽度，不溢出）。"""
    return _Capsule(text, max_width)


def _derive_tags(base_pred, best_result):
    """根据基准预测 vs 优化后预测，推导 3 个提升标签（数据驱动，不武断）。"""
    opt_by_label = {o.get("label"): o.get("value")
                    for o in best_result.get("outputs", [])}
    tags = []
    bw = str(base_pred.get("wetting_level", ""))
    ow = str(opt_by_label.get("润湿类别", ""))
    if bw and ow:
        try:
            if float(ow) > float(bw):
                tags.append("润湿等级 提升")
            elif float(ow) < float(bw):
                tags.append("润湿等级 降低")
            else:
                tags.append("润湿等级 持平")
        except (TypeError, ValueError):
            tags.append("润湿等级 持平")
    oc = str(opt_by_label.get("坍塌类别", ""))
    if oc == "冷":
        tags.append("坍塌风险 降低")
    elif oc == "热":
        tags.append("坍塌风险 升高")
    osb = str(opt_by_label.get("锡珠等级", ""))
    if osb in SOLDERBALL_MEANING:
        tags.append(f"锡珠等级 {SOLDERBALL_MEANING[osb]}")
    return tags or ["综合评分 提升"]


def _opt_hero(base_score, opt_score, base_pred, best_result):
    """优化概览 Hero：综合评分提升 + 绿色胶囊标签（浅绿圆角卡片）。"""
    try:
        b = float(base_score or 0)
    except (TypeError, ValueError):
        b = 0.0
    try:
        o = float(opt_score or 0)
    except (TypeError, ValueError):
        o = 0.0

    # 若基准分无效（用户未先跑预测），只显示优化分，不做虚假对比
    has_base = b > 0.01

    if has_base:
        delta = o - b
        if delta >= 0:
            delta_txt = f"+{_fmt(delta, 1)}"
            delta_color = ACCENT_GREEN.hexval()
            arrow_color = ACCENT_GREEN.hexval()
            delta_label = "提升"
        else:
            delta_txt = _fmt(delta, 1)
            delta_color = "#E53E3E"
            arrow_color = "#E53E3E"
            delta_label = "降低"

    # 左侧：评分区块
    if has_base:
        score_block = Paragraph(
            f'<font size="10" color="#86909C">综合评分</font><br/><br/>'
            f'<font size="22" color="#1D2129"><b>{_fmt(b, 1)}</b></font>'
            f'  <font size="18" color="{arrow_color}">'
            f'→ <b>{_fmt(o, 1)}</b></font><br/>'
            f'<font size="11" color="{delta_color}"><b>{delta_label} {delta_txt}</b></font>',
            _style(size=9, leading=20))
    else:
        score_block = Paragraph(
            f'<font size="10" color="#86909C">优化评分</font><br/><br/>'
            f'<font size="24" color="{ACCENT_GREEN.hexval()}"><b>{_fmt(o, 1)}</b></font>',
            _style(size=9, leading=20))

    # 右侧：胶囊标签（自动宽度，白底绿字）
    tags = _derive_tags(base_pred, best_result)
    pill_max_w = FRAME_W * 0.28  # 单个胶囊最大宽度
    pills = [_pill(t, pill_max_w) for t in tags]
    pill_row = Table([pills], colWidths=[pill_max_w] * len(tags))
    pill_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # 组合：左侧评分 + 右侧标签，外层浅绿圆角卡片
    inner = Table([[score_block, pill_row]],
                  colWidths=[FRAME_W * 0.45, FRAME_W * 0.55])
    inner.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, BORDER),
    ]))

    # 外层圆角容器（浅绿底 + 微圆角 + 细边框）
    hero_wrapper = RoundedBox(
        inner, width=FRAME_W,
        bg=colors.HexColor("#E8FFF3"), radius=10,
        pad_x=0, pad_y=0)
    return hero_wrapper


def _param_compare_table(base_input, rec):
    """配方参数对比：3 个优化维度（氧含量 / 粒度分布 / 助焊剂比例）。

    粒度分布为分类变量，左侧「粒度分布」单元格跨 4 行，
    每行展示一个粒度区间（<20µm / 20~38µm / 38~40µm / >40µm）的
    基准→推荐→调整百分比。
    """
    def _is_blank(v):
        """判定值为空/无效（含前端误传的 'NaN' 字符串），触发基准回退。"""
        if v is None or v == "" or v == "—" or v == "None":
            return True
        return str(v).strip().lower() == "nan"

    def bval(*keys, dec=1, unit=""):
        v = _get(base_input, *keys)
        if v is None or v == "—":
            return "—"
        try:
            fv = float(v)
            if fv != fv:
                return "—"
        except (TypeError, ValueError):
            return str(v)
        return f"{_fmt(v, dec)}{unit}"

    def rval(*keys, dec=1, unit=""):
        v = _get(rec, *keys)
        # 回退：推荐配方未改变的字段（如合金含量），从基准取
        if _is_blank(v):
            v = _get(base_input, *keys)
        if _is_blank(v):
            return "—"
        try:
            fv = float(v)
            if fv != fv:
                return "—"
        except (TypeError, ValueError):
            return str(v)
        return f"{_fmt(v, dec)}{unit}"

    def adj(b_keys=None, r_keys=None, dec=1, unit=""):
        b = _get(base_input, *(b_keys or [])) if b_keys else None
        r = _get(rec, *(r_keys or [])) if r_keys else None
        # 回退：推荐配方未改变的字段，从基准取
        if _is_blank(r) and r_keys:
            r = _get(base_input, *r_keys)
        if b is None or r is None or b == "" or r == "":
            return "—"
        try:
            fb, fr = float(b), float(r)
            if fb != fb or fr != fr:
                return "—"
        except (TypeError, ValueError):
            return "—"
        d = fr - fb
        if abs(d) < 1e-9:
            return "—"
        arrow = "↑" if d > 0 else "↓"
        sign = "+" if d > 0 else ""
        color = ACCENT_GREEN.hexval() if d > 0 else "#E53E3E"
        return Paragraph(
            f'<font color="{color}">{arrow} {sign}{_fmt(d, dec)}{unit}</font>',
            _style(size=9, alignment=1))

    # ── 粒度分布：4 个区间原始值 → 归一化百分比 ──
    PARTICLE_KEYS = [
        ("particle_size_real_lt_20", "<20µm"),
        ("particle_size_real_20_38", "20~38µm"),
        ("particle_size_real_38_40", "38~40µm"),
        ("particle_size_real_gt_40", ">40µm"),
    ]

    def _particle_pct(d):
        """从 dict 取 4 个粒度区间原始值，归一化为百分比列表 [(label, pct)]。"""
        raw = []
        for k, _ in PARTICLE_KEYS:
            try:
                raw.append(float(_get(d, k) or 0))
            except (TypeError, ValueError):
                raw.append(0.0)
        total = sum(raw) or 100.0
        return [(label, v / total * 100) for label, v in zip(
            [lbl for _, lbl in PARTICLE_KEYS], raw)]

    base_parts = _particle_pct(base_input)
    # 推荐粒度分布：优先用前端传的 particle_distribution（[{label,value:"32.0%"}]），
    # 否则从 rec 的粒度原始字段算
    rec_dist = rec.get("particle_distribution")
    if isinstance(rec_dist, list) and rec_dist:
        rec_parts = []
        for item in rec_dist:
            lbl = item.get("label", "")
            val = item.get("value", 0)
            try:
                val = float(str(val).replace("%", "").strip())
            except (TypeError, ValueError):
                val = 0.0
            rec_parts.append((lbl, val))
    else:
        rec_parts = _particle_pct(rec)

    # 单行：氧含量
    oxygen_row = [
        "氧含量",
        bval("oxygen_real", dec=4),
        rval("oxygen_real", dec=4),
        adj(b_keys=("oxygen_real",), r_keys=("oxygen_real",), dec=4),
    ]
    # 单行：助焊剂比例（合金含量 = 100 - 助焊剂，不单列）
    flux_row = [
        "助焊剂比例",
        bval("flux_percent", dec=1, unit="%"),
        rval("flux_percent", dec=1, unit="%"),
        adj(b_keys=("flux_percent",), r_keys=("flux_percent",), dec=1, unit="%"),
    ]

    # 粒度分布 4 个子行：每行 → [标签占位, 基准, 推荐, 调整]
    particle_rows = []
    for i, (blabel, bpct) in enumerate(base_parts):
        rpct = rec_parts[i][1] if i < len(rec_parts) else 0.0
        d = rpct - bpct
        if abs(d) < 0.05:
            adj_cell = "—"
        else:
            arrow = "↑" if d > 0 else "↓"
            sign = "+" if d > 0 else ""
            color = ACCENT_GREEN.hexval() if d > 0 else "#E53E3E"
            adj_cell = Paragraph(
                f'<font color="{color}">{arrow} {sign}{_fmt(d, 1)}%</font>',
                _style(size=9, alignment=1))
        particle_rows.append([
            "",  # 第 0 列留给 SPAN 合并的「粒度分布」
            f"{blabel}  {_fmt(bpct, 1)}%",
            f"{blabel}  {_fmt(rpct, 1)}%",
            adj_cell,
        ])

    # data 行序：0表头 / 1氧含量 / 2~5粒度 / 6助焊剂
    rows = [oxygen_row]
    for pr in particle_rows:
        rows.append(pr)
    rows.append(flux_row)

    # 用 SPAN 把「粒度分布」合并跨 4 行（data 行 2~5，即 (0,2)-(0,5)）
    span_style = [("SPAN", (0, 2), (0, 5))]
    return clean_table(
        headers=["参数", "基准配方", "推荐配方", "调整"],
        rows=rows,
        col_ratios=[1.2, 1.1, 1.1, 1],
        extra_style=span_style,
    )


def _sensitivity_bars(impact_groups):
    """参数敏感性排序：横向进度条（加粗 + 区分度优化）。"""
    ranges = []
    for g in impact_groups:
        r = g.get("raw_range")
        if r is None:
            r = (g.get("impact_pct") or 0) / 100.0
        try:
            ranges.append(float(r))
        except (TypeError, ValueError):
            ranges.append(0.0)
    max_r = max(ranges) if ranges else 1.0
    if max_r <= 0:
        max_r = 1.0

    blocks = []
    for g, r in zip(impact_groups, ranges):
        # 保证最小 25% 可见宽度（原 15% 太细），最大 95%
        pct = max(25, min(95, int(r / max_r * 100)))
        level = "高影响" if pct >= 66 else ("中影响" if pct >= 33 else "低影响")
        name = g.get("name", "-")
        label = Table(
            [[_p(name, size=9, textColor=TEXT_LABEL),
              _p(level, size=9, alignment=2)]],
            colWidths=[FRAME_W * 0.7, FRAME_W * 0.3])
        label.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        # 进度条加粗到 14pt 高（原 10pt 太细）
        bar = Table([["", ""]],
                    colWidths=[FRAME_W * pct / 100.0,
                               FRAME_W * (100 - pct) / 100.0],
                    rowHeights=[14])
        bar.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), ACCENT_GREEN),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#E8EAED")),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        blocks.append(label)
        blocks.append(bar)
        blocks.append(Spacer(1, 5 * mm))
    return blocks


def _suggestion_block(title, body):
    """优化建议：左侧绿色竖条 callout（精致版）。"""
    p = Paragraph(
        f'<font color="{TEXT_DARK.hexval()}" size="10"><b>{title}</b></font>'
        f'<br/><font size="9.5" color="#4E5969">{body}</font>',
        _style(size=9.5, leading=15))
    t = Table([[p]], colWidths=[FRAME_W - 24])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6FFED")),
        ("LINEBEFORE", (0, 0), (0, 0), 3.5, ACCENT_GREEN),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def _get(d, *keys, default=None):
    """从字典中按多个候选 key 查找值（兼容 camelCase / snake_case / 中文）。
    用法：_get(data, "wetting_level", "wettingLevel", "润湿等级", default="—")
    """
    if not d:
        return default
    for k in keys:
        v = d.get(k)
        if v is not None and v != "" and v != "—":
            return v
    return default


# ════════════════════════════════════════════════════════
#  最优参数结果（6 宫格卡片）
# ════════════════════════════════════════════════════════

def _output_value(best_result, *keywords):
    """从 best_result.outputs 中按 label 关键字匹配取值。"""
    for o in best_result.get("outputs", []) or []:
        label = str(o.get("label", ""))
        if any(k in label for k in keywords):
            val = o.get("value")
            return val if val is not None else "—"
    return None


def _grid_card(label, value, width):
    """单个浅灰小卡片：上标签 + 下数值。"""
    inner = Table([
        [_p(label, size=9, textColor=TEXT_SECONDARY)],
        [_p(str(value), size=14, font=_FONT, textColor=TEXT_DARK)],
    ], colWidths=[width])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFBFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 2),
        ("BOTTOMPADDING", (0, 1), (0, 1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return inner


def _opt_param_grid(best_result, rec, base_input):
    """最优参数结果：5 宫格卡片（不含合金成分，用户确认删减）。

    数据来源：
      - 氧含量/粒度方案：best_result.xText + recommended_params.particle_profile
      - 黏度初值(Pa) / Ti / 锡粉规格：best_result.outputs
      - 助焊剂比例：recommended_params
    """
    x_text = best_result.get("xText", "") or ""
    m_o = re.search(r"氧含量\s*([0-9.]+)", x_text)
    m_p = re.search(r"(P\d+)", x_text)
    oxygen = m_o.group(1) if m_o else None
    profile = m_p.group(1) if m_p else None
    # 回退：从 recommended_params 取 particle_profile
    if not profile:
        profile = rec.get("particle_profile") or rec.get("particleProfile")
    if oxygen and profile:
        v1 = f"O {oxygen} / {profile}"
    elif oxygen:
        v1 = f"O {oxygen}"
    elif profile:
        v1 = profile
    else:
        v1 = _get(rec, "oxygen_real") or _get(base_input, "oxygen_real") or "—"

    visc = _output_value(best_result, "粘", "黏", "黏度")
    ti = _output_value(best_result, "Ti")
    powder = _output_value(best_result, "锡粉", "规格")
    flux = _get(rec, "flux_percent")

    # 5 宫格（去掉合金成分）
    cards = [
        ("氧含量 / 粒度方案", v1),
        ("黏度初值 (Pa)", visc if visc is not None else "—"),
        ("Ti 参数", ti if ti is not None else "—"),
        ("锡粉规格", powder if powder is not None else "—"),
        ("助焊剂比例", f"{_fmt(flux, 1)}%" if flux is not None else "—"),
    ]
    cw = FRAME_W / 3 - 6
    cells = [_grid_card(l, v, cw) for l, v in cards]
    # 5 格布局：上排 3 个 + 下排 2 个居中
    row2_cells = cells[3:5] + [_p("", size=1)]  # 填充占位
    grid = Table([cells[0:3], row2_cells], colWidths=[FRAME_W / 3] * 3)
    grid.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return grid


# ════════════════════════════════════════════════════════
#  数据表格（干净现代风格，独立圆角容器，全部居中）
# ════════════════════════════════════════════════════════

def clean_table(headers, rows, col_ratios=None,
                header_bg=TABLE_HEADER_BG, extra_style=None):
    """
    专业数据表格：
    - 表头加深灰底 + 字体加粗
    - 所有列统一居中对齐
    - 用 RoundedBox 包裹，形成独立圆角容器
    - extra_style: 额外 TableStyle 命令（如 SPAN 跨行）
    """
    data = [headers] + list(rows)
    n_cols = len(headers)
    if col_ratios:
        total = sum(col_ratios)
        widths = [TABLE_W * r / total for r in col_ratios]
    else:
        widths = [TABLE_W / n_cols] * n_cols

    t = Table(data, colWidths=widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT_DARK),
        ("FONTNAME", (0, 0), (-1, 0), _FONT),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),       # 全部居中
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (-1, -1), _FONT_BODY),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#FAFBFC")]),
    ]
    if extra_style:
        style_cmds.extend(extra_style)
    t.setStyle(TableStyle(style_cmds))
    return RoundedBox(t, width=TABLE_W + 2 * TABLE_PAD,
                      bg=TABLE_BOX_BG, radius=6, pad_x=TABLE_PAD, pad_y=TABLE_PAD)


# ════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════

def _fmt(value, decimals=2):
    try:
        v = float(value)
        # NaN / Inf 防御
        if v != v or abs(v) == float('inf'):
            return "—"
        if v == int(v) and decimals <= 1:
            return str(int(v))
        return f"{v:.{decimals}f}"
    except (TypeError, ValueError):
        return str(value) if value is not None else "—"


def _fmt_metal(value, decimals=3):
    try:
        v = float(value)
        if abs(v) < 0.0001:
            return "0"
        return f"{v:.{decimals}f}"
    except (TypeError, ValueError):
        return str(value) if value is not None else "-"


def _build_doc(buf, on_page):
    frame = Frame(
        18 * mm, 15 * mm,
        PAGE_W - 36 * mm,
        PAGE_H - 54 * mm,
        id='main',
    )
    template = PageTemplate(
        id='Main', frames=[frame],
        onPage=lambda c, d: (_draw_footer(c, d), on_page(c, d)),
    )
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=0, rightMargin=0,
        topMargin=0, bottomMargin=0,
    )
    doc.addPageTemplates([template])
    return doc


# ════════════════════════════════════════════════════════
#  性能预测报告
# ════════════════════════════════════════════════════════

def generate_prediction_report(
    predictions: Dict[str, Any],
    score: float,
    input_features: Dict[str, Any],
    execution_time_ms: float = 0,
    operator: str = "Admin",
) -> bytes:
    buf = io.BytesIO()
    rid = f"PRD{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def on_page(canvas, doc):
        _draw_header(canvas, doc,
                     title="锡膏性能预测报告",
                     report_id=rid,
                     operator=operator,
                     title_color=PRIMARY)

    doc = _build_doc(buf, on_page)
    elements = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 卡片 1：输入配方参数 ─────────────────────────
    param_rows = [
        ["助焊膏型号", str(input_features.get("flux_type",
                     input_features.get("flux_paste", "-")))],
        ["助焊剂比例", f"{_fmt(input_features.get('flux_percent'), 1)}%"],
        ["合金含量", f"{_fmt(input_features.get('alloy_content'), 1)}%"],
        ["Ag / Cu / Pb / Fe",
         f"{_fmt_metal(input_features.get('ag'))} / "
         f"{_fmt_metal(input_features.get('cu'))} / "
         f"{_fmt_metal(input_features.get('pb'))} / "
         f"{_fmt_metal(input_features.get('fe'))}"],
        ["Bi / Sb",
         f"{_fmt_metal(input_features.get('bi'))} / "
         f"{_fmt_metal(input_features.get('sb'))}"],
        ["氧含量",
         f"{_fmt(input_features.get('oxygen_real') or input_features.get('oxygen'), 4)}%"],
    ]
    param_table = clean_table(
        headers=["参数名称", "数值"],
        rows=param_rows,
        col_ratios=[1.3, 1],
    )
    elements.append(Spacer(1, 5 * mm))
    elements.append(card("输入配方参数", [param_table]))

    # ── 卡片 2：预测结果总览（2 列，无武断判定）─────────
    pred_rows = [
        ["黏度初值（Pa.s）", _fmt(predictions.get('viscosity'), 3)],
        ["触变指数（TI）", _fmt(predictions.get('ti'), 4)],
        ["锡粉规格", str(predictions.get("powder_spec", "-"))],
        ["润湿等级", str(predictions.get("wetting_level", "-"))],
        ["坍塌类别", str(predictions.get("collapse_category", "-"))],
        ["锡珠等级", str(predictions.get("solderball_level", "-"))],
    ]
    pred_table = clean_table(
        headers=["性能指标", "预测结果"],
        rows=pred_rows,
        col_ratios=[1.4, 1],
    )
    elements.append(Spacer(1, 8 * mm))
    elements.append(card("预测结果总览", [pred_table]))

    # ── 卡片 3：推理信息 ─────────────────────────────
    exec_display = f"{_fmt(execution_time_ms, 1)} ms" if execution_time_ms else "—"
    info_rows = [
        ["推理耗时", exec_display],
        ["生成时间", now_str],
        ["操作人", operator],
    ]
    info_table = clean_table(
        headers=["项目", "详情"],
        rows=info_rows,
        col_ratios=[1, 1.2],
    )
    elements.append(Spacer(1, 8 * mm))
    elements.append(card("推理信息", [info_table]))

    doc.build(elements)
    return buf.getvalue()


# ════════════════════════════════════════════════════════
#  配方优化报告
# ════════════════════════════════════════════════════════

def generate_optimization_report(
    base_predictions: Dict[str, Any],
    base_input: Dict[str, Any],
    best_result: Dict[str, Any],
    recommended_params: Optional[Dict[str, Any]] = None,
    impact_groups: Optional[List[Dict]] = None,
    operator: str = "Admin",
) -> bytes:
    """
    配方优化报告（v11 — 严格对齐设计稿）。

    布局结构（与设计稿一一对应）：
      1. 页眉：黑色大标题 + 绿色副标题 + 编号/时间/操作人
      2. Hero 卡片：综合评分 + 3 个胶囊标签
      3. 配方参数对比（4 列表，固定 3 行）
      4. 预期性能对比（3 列表，含含义后缀）
      5. 参数敏感性排序（进度条）
      6. 优化建议（2 条 callout）
      7. 单行免责声明
    """
    buf = io.BytesIO()
    rid = f"OPT{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def on_page(canvas, doc):
        _draw_header(canvas, doc,
                     title="锡膏配方优化报告",
                     report_id=rid,
                     operator=operator,
                     title_color=ACCENT_GREEN)

    doc = _build_doc(buf, on_page)
    elements = []

    # ── 分数提取 & 尺度自动修正 ───────────────────────
    # 基准分来自后端预测，是 0~10 分制（兼容多种字段名）
    _bp = base_predictions or {}
    _raw_base = _get(_bp, "score", "baseScore", "base_score")
    try:
        base_score = float(_raw_base or 0)
    except (TypeError, ValueError):
        base_score = 0.0

    # 优化分可能来自前端 normalizeScores (0~1) 或后端 (0~10)
    # 自动检测 ×10 修正：
    #   - 若 opt_score 在 (0, 1.5] 区间（明显是 0~1 归一化），无条件 ×10
    #   - 或 opt_score < 2 且 base_score > 5（旧条件，兼容）
    try:
        opt_score = float(best_result.get("score", 0))
    except (TypeError, ValueError):
        opt_score = 0.0
    if (0 < opt_score <= 1.5) or (opt_score < 2 and base_score > 5):
        opt_score = min(opt_score * 10, 10.0)  # 上限 10 分

    if not best_result:
        elements.append(Spacer(1, 8 * mm))
        elements.append(green_section(
            "优化结果",
            [_p("暂无优化结果数据。", textColor=TEXT_SECONDARY)]))
        doc.build(elements)
        return buf.getvalue()

    rec = recommended_params or {}

    # ══════════════════════════════════════════════════
    #  ① 最优参数结果（5 宫格卡片，不含合金成分）
    # ══════════════════════════════════════════════════
    elements.append(Spacer(1, 5 * mm))
    elements.append(green_section("最优参数结果",
                                  [_opt_param_grid(best_result, rec, base_input)],
                                  with_line=False))

    # ══════════════════════════════════════════════════
    #  ② 配方参数对比（设计稿：4 列 × 3 行）
    # ══════════════════════════════════════════════════
    elements.append(Spacer(1, 7 * mm))
    elements.append(green_section("配方参数对比",
                                  [_param_compare_table(base_input, rec)]))

    # ══════════════════════════════════════════════════
    #  ③ 预期性能对比（当前 vs 优化，带含义后缀）
    # ══════════════════════════════════════════════════
    opt_by_label = {o.get("label"): o.get("value")
                    for o in best_result.get("outputs", [])}
    # 兼容字段名：前端可能传 camelCase 或 snake_case
    _bp = base_predictions or {}
    perf_rows = [
        ["润湿等级",
         str(_get(_bp, "wetting_level", "wettingLevel", "润湿等级", "润湿类别", default="—")),
         str(opt_by_label.get("润湿类别",
               opt_by_label.get("润湿等级", "-")))],
        ["坍塌类别",
         str(_get(_bp, "collapse_category", "collapseCategory", "坍塌类别", default="—")),
         str(opt_by_label.get("坍塌类别", "-"))],
        ["锡珠等级",
         str(_get(_bp, "solderball_level", "solderballLevel", "锡珠等级", default="—")),
         str(opt_by_label.get("锡珠等级", "-"))],
    ]
    perf_table = clean_table(
        headers=["性能指标", "当前预测", "优化预期"],
        rows=perf_rows,
        col_ratios=[1.3, 1, 1.2],
    )
    elements.append(Spacer(1, 7 * mm))
    elements.append(green_section("预期性能对比", [perf_table]))

    # ══════════════════════════════════════════════════
    #  ④ 参数敏感性排序（进度条）
    # ══════════════════════════════════════════════════
    if impact_groups:
        elements.append(Spacer(1, 7 * mm))
        elements.append(green_section("参数敏感性排序",
                                      _sensitivity_bars(impact_groups)))

    # ══════════════════════════════════════════════════
    #  ⑤ 优化建议（设计稿只有 2 条：整体建议 + 优化方向）
    # ══════════════════════════════════════════════════
    suggestions = [
        ("整体建议",
         "预测性能良好，各项指标均在历史正常范围内，建议按推荐配方进行小批量试产。"),
        ("优化方向",
         "若需进一步提升润湿等级，可将助焊剂比例微调至 11.4% ~ 11.7% 区间。"),
    ]
    sug_contents = [_suggestion_block(t, b) for t, b in suggestions]
    elements.append(Spacer(1, 7 * mm))
    elements.append(green_section("优化建议", sug_contents))

    doc.build(elements)
    return buf.getvalue()
