"""Inline SVG charts for the site, styled by site.css."""
from __future__ import annotations

import html
import math

import pandas as pd

from f1pred.web.data import Entry, Row


def _open(label: str, width: int, height: float) -> str:
    return f'<svg class="chart" viewBox="0 0 {width} {height:.0f}" role="img" aria-label="{html.escape(label)}">'


def _vline(x: float, y1: float, y2: float) -> str:
    return f'<line class="gridline" x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" />'


def chance_bars(rows: list[Row]) -> str:
    if not rows:
        return ""
    ceiling = max(max(r.podium for r in rows), max(r.win for r in rows))
    scale = max(20, math.ceil(ceiling / 20) * 20)
    width, row_h, pad_l, pad_r, head = 640, 28, 64, 48, 24
    plot = width - pad_l - pad_r
    height = head + row_h * len(rows)
    parts = [_open(f"Win and podium chance for the leading {len(rows)} drivers", width, height)]
    for step in range(5):
        x = pad_l + plot * step / 4
        parts.append(_vline(x, head - 6, height - 4))
        parts.append(f'<text class="axis" x="{x:.1f}" y="{head - 12}" text-anchor="middle">{scale * step // 4}</text>')
    for i, r in enumerate(rows):
        y = head + i * row_h
        podium, win = plot * min(r.podium, scale) / scale, plot * min(r.win, scale) / scale
        parts.append(f'<text class="axis" x="14" y="{y + 17}" text-anchor="end">{r.pos}</text>')
        parts.append(f'<text class="code" x="22" y="{y + 18}">{html.escape(r.code)}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y + 4}" width="{podium:.1f}" height="16" fill="{r.color}" '
                     f'fill-opacity=".3" />')
        parts.append(f'<rect x="{pad_l}" y="{y + 4}" width="{win:.1f}" height="16" fill="{r.color}" />')
        parts.append(f'<text class="axis" x="{pad_l + podium + 6:.1f}" y="{y + 17}">{r.podium:.0f}</text>')
        if win >= 30:
            parts.append(f'<text class="val" x="{pad_l + win - 6:.1f}" y="{y + 17}" text-anchor="end" '
                         f'fill="{r.on_color}">{r.win:.0f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def dumbbell(races: pd.DataFrame) -> str:
    width, row_h, pad_l, pad_r, head = 520, 30, 150, 44, 26
    plot = width - pad_l - pad_r
    lo = min(0.0, float(races[["Spearman", "GridSpearman"]].min().min()))
    height = head + row_h * len(races)

    def x(v: float) -> float:
        return pad_l + plot * (v - lo) / (1 - lo)

    parts = [_open("Order match per race, model against grid order", width, height)]
    for step in range(5):
        v = lo + (1 - lo) * step / 4
        parts.append(_vline(x(v), head - 6, height - 4))
        parts.append(f'<text class="axis" x="{x(v):.1f}" y="{head - 12}" text-anchor="middle">{v:.2f}</text>')
    for i, r in enumerate(races.itertuples(index=False)):
        y = head + i * row_h + 13
        name = html.escape(str(r.EventName).removesuffix(" Grand Prix"))
        tip = (f"R{r.RoundNumber} {name}: model {r.Spearman:.2f}, grid {r.GridSpearman:.2f}"
               f"{'' if r.Live else ' (made after the race)'}")
        parts.append(f"<g><title>{tip}</title>")
        parts.append(f'<text class="axis" x="22" y="{y + 4}" text-anchor="end">{r.RoundNumber}</text>')
        parts.append(f'<text class="label" x="30" y="{y + 5}">{name}</text>')
        parts.append(f'<line class="link" x1="{x(r.GridSpearman):.1f}" y1="{y}" x2="{x(r.Spearman):.1f}" y2="{y}" />')
        parts.append(f'<circle class="gridpt" cx="{x(r.GridSpearman):.1f}" cy="{y}" r="5" />')
        parts.append(f'<circle class="model" cx="{x(r.Spearman):.1f}" cy="{y}" r="5" />')
        if r.Live:
            parts.append(f'<text class="live" x="{width - 2}" y="{y + 4}" text-anchor="end">LIVE</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def calibration(cal: pd.DataFrame) -> str:
    width, row_h, pad_l, pad_r, head = 520, 42, 74, 56, 26
    plot = width - pad_l - pad_r
    height = head + row_h * len(cal)
    parts = [_open("Predicted podium chance against how often it happened", width, height)]
    for step in range(5):
        xv = pad_l + plot * step / 4
        parts.append(_vline(xv, head - 6, height - 4))
        parts.append(f'<text class="axis" x="{xv:.1f}" y="{head - 12}" text-anchor="middle">{step * 25}</text>')
    for i, (band, r) in enumerate(cal.iterrows()):
        y = head + i * row_h
        parts.append(f"<g><title>Said {band}: averaged {r.Said:.0f}%, happened {r.Did:.0f}% "
                     f"of {int(r.N)} times</title>")
        parts.append(f'<text class="axis" x="{pad_l - 10}" y="{y + 23}" text-anchor="end">{band}</text>')
        parts.append(f'<rect class="said" x="{pad_l}" y="{y + 4}" width="{plot * r.Said / 100:.1f}" height="14" />')
        parts.append(f'<rect class="did" x="{pad_l}" y="{y + 20}" width="{plot * r.Did / 100:.1f}" height="14" />')
        parts.append(f'<text class="axis" x="{pad_l + plot * max(r.Said, r.Did) / 100 + 8:.1f}" y="{y + 23}">'
                     f'n={int(r.N)}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def driver_season(entries: list[Entry], color: str) -> str:
    if not entries:
        return ""
    width, height, pad_l, pad_r, top, bottom = 640, 240, 36, 16, 12, 28
    plot_w, plot_h = width - pad_l - pad_r, height - top - bottom
    worst = max([20, *(e.row.pos for e in entries), *(int(e.row.finish) for e in entries if e.row.classified)])

    def x(i: int) -> float:
        return pad_l + (plot_w * i / (len(entries) - 1) if len(entries) > 1 else plot_w / 2)

    def y(p: int) -> float:
        return top + plot_h * (p - 1) / (worst - 1)

    parts = [_open("Predicted and actual finish by round", width, height)]
    for p in (1, 5, 10, 15, 20):
        parts.append(f'<line class="gridline" x1="{pad_l}" y1="{y(p):.1f}" x2="{width - pad_r}" y2="{y(p):.1f}" />')
        parts.append(f'<text class="axis" x="{pad_l - 8}" y="{y(p) + 4:.1f}" text-anchor="end">{p}</text>')
    for i, e in enumerate(entries):
        parts.append(f'<text class="axis" x="{x(i):.1f}" y="{height - 6}" text-anchor="middle">{e.race.rnd}</text>')
    predicted = " ".join(f"{x(i):.1f},{y(e.row.pos):.1f}" for i, e in enumerate(entries))
    parts.append(f'<polyline class="pred" points="{predicted}" />')
    segment: list[str] = []
    for i, e in enumerate([*entries, None]):
        if e is not None and e.row.classified:
            segment.append(f"{x(i):.1f},{y(int(e.row.finish)):.1f}")
            continue
        if len(segment) > 1:
            parts.append(f'<polyline class="act" stroke="{color}" points="{" ".join(segment)}" />')
        segment = []
    for i, e in enumerate(entries):
        if e.row.classified:
            tip = html.escape(f"R{e.race.rnd} {e.race.short_name}: predicted {e.row.pos}, finished {e.row.finish}")
            parts.append(f'<circle class="dot" cx="{x(i):.1f}" cy="{y(int(e.row.finish)):.1f}" r="4" '
                         f'fill="{color}"><title>{tip}</title></circle>')
    parts.append("</svg>")
    return "".join(parts)
