"""Team colours, the shareable race page and its PNG."""
from __future__ import annotations

from pathlib import Path

from f1pred import config

SCREENSHOT_WIDTH = 960
BROWSER_CHANNELS = ["msedge", "chrome"]

# Constructor colours as published by FastF1 for 2026.
TEAM_COLORS = {
    "Alpine": "#ff87bc",
    "Aston Martin": "#00665f",
    "Audi": "#ff2d00",
    "Cadillac": "#444444",
    "Ferrari": "#e80020",
    "Haas F1 Team": "#b6babd",
    "McLaren": "#ff8000",
    "Mercedes": "#27f4d2",
    "Racing Bulls": "#fcd700",
    "Red Bull Racing": "#0600ef",
    "Williams": "#00a0dd",
}
FALLBACK_COLOR = "#8a8a8a"


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _luma(rgb: tuple[int, int, int]) -> float:
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def _mix(rgb: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(c + (t - c) * amount for c, t in zip(rgb, target))


def team_colors(team: str) -> tuple[str, str]:
    """Team colour adjusted so it stays visible on paper and on a dark screen."""
    base = _rgb(TEAM_COLORS.get(team, FALLBACK_COLOR))
    light, dark = base, base
    for _ in range(6):
        if _luma(light) <= 0.62:
            break
        light = _mix(light, (0, 0, 0), 0.22)
    for _ in range(6):
        if _luma(dark) >= 0.38:
            break
        dark = _mix(dark, (255, 255, 255), 0.3)
    return _hex(light), _hex(dark)


def on_color(value: str) -> str:
    """Ink that stays readable on top of a team colour."""
    return "#10131a" if _luma(_rgb(value)) > 0.55 else "#ffffff"


def screenshot(html_path: Path, width: int = SCREENSHOT_WIDTH, out: Path | None = None) -> Path | None:
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        print("Skipping the PNG: `pip install playwright` to get one.")
        return None
    png_path = Path(out) if out else html_path.with_suffix(".png")
    with sync_playwright() as p:
        for channel in BROWSER_CHANNELS:
            try:
                browser = p.chromium.launch(channel=channel)
                break
            except Error:
                continue
        else:
            print("Skipping the PNG: no Edge or Chrome found.")
            return None
        page = browser.new_page(viewport={"width": width, "height": 800}, device_scale_factor=2, color_scheme="dark")
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.screenshot(path=png_path, full_page=True)
        browser.close()
    return png_path


def run(season: int, rnd: int, png: bool = True) -> Path:
    from f1pred.web import build as web
    csv_path = config.prediction_path(season, rnd, ".csv")
    if not csv_path.exists():
        raise SystemExit(f"No saved prediction at {csv_path}; run `predict` first.")
    out_path = csv_path.with_suffix(".html")
    out_path.write_text(web.standalone_race(season, rnd), encoding="utf-8", newline="\n")
    print(f"Wrote {out_path}\nOpen it in a browser, or send the path to Claude to publish a shareable link.")
    png_path = screenshot(out_path) if png else None
    if png_path:
        print(f"Wrote {png_path}, ready to send as a picture.")
    return out_path
