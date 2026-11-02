"""1200x630 link-preview image per race: the predicted podium, and the result once it's in."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from f1pred.web import data

FONTS = Path(__file__).parent / "fonts"
SIZE = (1200, 630)
BG, PANEL, INK, INK_2, INK_3, ACCENT = "#0a0a0d", "#15151b", "#f4f4f6", "#b8b8c4", "#7d7d8b", "#e10600"
PAD = 64


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"SpaceGrotesk-{weight}.ttf"), size)


def _fit(draw: ImageDraw.ImageDraw, text: str, weight: str, size: int, width: int) -> ImageFont.FreeTypeFont:
    font = _font(weight, size)
    while size > 24 and draw.textlength(text, font=font) > width:
        size -= 4
        font = _font(weight, size)
    return font


def wordmark(draw: ImageDraw.ImageDraw, at: tuple[int, int], size: int) -> None:
    font = _font("Bold", size)
    draw.text(at, "PARC", font=font, fill=INK)
    draw.text((at[0] + draw.textlength("PARC ", font=font), at[1]), "FERMÉ", font=font, fill=ACCENT)


def icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    font = _font("Bold", round(size * 0.62))
    x = (size - draw.textlength("PF", font=font)) / 2
    y = size / 2
    draw.text((x, y), "P", font=font, fill=INK, anchor="lm")
    draw.text((x + draw.textlength("P", font=font), y), "F", font=font, fill=ACCENT, anchor="lm")
    return img


def render(race: data.Race) -> Image.Image:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SIZE[0], 10], fill=ACCENT)

    wordmark(draw, (PAD, 40), 38)
    status = "LIVE · predicted before the race" if race.live else "Made after the race"
    eyebrow = f"ROUND {race.rnd} · {race.season}"
    draw.text((SIZE[0] - PAD, 52), eyebrow, font=_font("Medium", 26), fill=INK_3, anchor="ra")

    name = race.name.upper()
    draw.text((PAD, 104), name, font=_fit(draw, name, "Bold", 84, SIZE[0] - 2 * PAD), fill=INK)
    draw.text((PAD, 206), status, font=_font("Medium", 28), fill=ACCENT if race.live else INK_3)

    gap, top, bottom = 24, 270, 500
    width = (SIZE[0] - 2 * PAD - 2 * gap) // 3
    for i, row in enumerate(race.podium):
        x = PAD + i * (width + gap)
        draw.rectangle([x, top, x + width, bottom], fill=PANEL)
        draw.rectangle([x, top, x + width, top + 8], fill=row.color)
        draw.text((x + 24, top + 26), f"P{row.pos}", font=_font("Medium", 26), fill=INK_3)
        draw.text((x + 24, top + 52), row.code, font=_font("Bold", 76), fill=INK)
        draw.text((x + 24, top + 150), f"{data.chance(row.win)} to win", font=_font("Bold", 32), fill=INK_2)
        if row.finish:
            draw.text((x + 24, top + 190), row.finish_text, font=_font("Medium", 24), fill=INK_3)

    if race.verdict is not None:
        foot = race.verdict.lines[0]
        if race.winner and not race.pick_hit:
            foot += f" · {race.winner} won"
    else:
        foot = f"Favourite {race.favourite.code} at {data.chance(race.favourite.win)} · result pending"
    draw.text((PAD, 532), foot, font=_fit(draw, foot, "Bold", 34, SIZE[0] - 2 * PAD), fill=INK)
    return img


def save(race: data.Race, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    render(race).save(path, "PNG", optimize=True)
    return path
