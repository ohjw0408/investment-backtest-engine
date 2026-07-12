"""Compose Google Play graphics from captured Money Milestone screenshots.

디자인 방향(토스/도미노풍): 넓은 여백 · 소프트 그라디언트 블롭 배경 ·
떠 있는 기기(큰 소프트 섀도우) · 컬러 pill 태그 · 슬라이드당 한 메시지.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store-assets" / "play-store-graphics-20260704"
RAW = OUT / "raw"
ICON = ROOT / "store-assets" / "play-icon-512.png"

REG = Path(r"C:\Windows\Fonts\malgun.ttf")
BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")
KR = Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    choices = [BOLD if bold else KR, KR, REG]
    for p in choices:
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            continue
    return ImageFont.load_default()


def rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.strip().lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    return (int(ar + (br - ar) * t), int(ag + (bg - ag) * t), int(ab + (bb - ab) * t))


def gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(img)
    tr, tg, tb = rgb(top)
    br, bg, bb = rgb(bottom)
    for y in range(h):
        t = y / max(1, h - 1)
        draw.line((0, y, w, y), fill=(int(tr + (br - tr) * t), int(tg + (bg - tg) * t), int(tb + (bb - tb) * t)))
    return img


def cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = img.size
    tw, th = size
    scale = max(tw / w, th / h)
    resized = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def rounded_paste(base, img, box, radius):
    x, y, w, h = box
    fit = cover(img, (w, h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    base.paste(fit, (x, y), mask)


def text(draw, xy, s, size, fill, bold=False, anchor=None, align="left"):
    draw.text(xy, s, font=font(size, bold), fill=fill, anchor=anchor, align=align)


def multiline(draw, x, y, lines, size, fill, bold=False, spacing=8, max_width=None):
    f = font(size, bold)
    yy = y
    for line in lines:
        if max_width:
            line = fit_line(draw, line, f, max_width)
        draw.text((x, yy), line, font=f, fill=fill)
        yy += int(size * 1.24) + spacing
    return yy


def fit_line(draw, s, f, max_width):
    if draw.textlength(s, font=f) <= max_width:
        return s
    out = ""
    for ch in s:
        if draw.textlength(out + ch + "…", font=f) > max_width:
            return out + "…"
        out += ch
    return out


def blob(base, cx, cy, r, color, alpha):
    """부드럽게 번진 원형 컬러 블롭 — 토스풍 배경 악센트."""
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*rgb(color), alpha))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(int(r * 0.42))))


def pill(draw, x, y, label, bg, fg="#FFFFFF", size=27):
    f = font(size, True)
    tw = int(draw.textlength(label, font=f))
    px, ph = 24, size + 24
    draw.rounded_rectangle((x, y, x + tw + px * 2, y + ph), radius=ph // 2, fill=bg)
    draw.text((x + px, y + (ph - size) // 2 - 3), label, font=f, fill=fg)
    return ph


def floating_frame(base, shot_path, x, y, w, h, radius=78, bezel=18,
                   blur=52, shadow_alpha=78, dy=40):
    """큰 소프트 드롭섀도우로 기기를 띄운다."""
    shot = Image.open(shot_path).convert("RGB")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        (x, y + dy, x + w, y + h + dy), radius=radius, fill=(15, 23, 42, shadow_alpha))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=(11, 14, 20, 255))
    ix, iy, iw, ih = x + bezel, y + bezel, w - bezel * 2, h - bezel * 2
    rounded_paste(base, shot, (ix, iy, iw, ih), max(20, radius - bezel))
    d.rounded_rectangle((ix, iy, ix + iw, iy + ih), radius=max(20, radius - bezel),
                        outline=(255, 255, 255, 46), width=2)


# (key, tag, title, subtitle, raw, accent)
PHONE_SPECS = [
    ("01-home", "홈", "자산배분 포트폴리오", "내 자산과 수익률을 한눈에", "phone-01-home.png", "#F97316"),
    ("02-holdings", "내 자산", "주식·ETF·금·채권", "국내외 인기 자산을 함께 관리", "phone-03-holdings.png", "#059669"),
    ("03-rebalance", "리밸런싱", "목표 비중 리밸런싱", "흔들린 자산군을 바로 확인", "phone-04-rebalance.png", "#4F46E5"),
    ("04-backtest", "백테스트", "전략은 백테스트로", "과거 데이터로 먼저 점검", "phone-05-backtest.png", "#0EA5E9"),
    ("05-macro", "거시지표", "금리·물가 한 화면에", "시장 흐름까지 놓치지 않게", "phone-06-macro.png", "#DB2777"),
]


def paint_bg(size, accent):
    """거의 흰 배경 + 악센트 살짝 밴 톤 + 소프트 블롭 2개."""
    W, H = size
    img = gradient(size, "#FFFFFF", "#%02X%02X%02X" % mix("#FFFFFF", accent, 0.06)).convert("RGBA")
    blob(img, int(W * 0.86), int(H * 0.17), int(W * 0.52), accent, 60)
    blob(img, int(W * 0.10), int(H * 0.93), int(W * 0.46), accent, 34)
    return img


def compose_phone():
    for key, tag, title, subtitle, raw_name, accent in PHONE_SPECS:
        W, H = 1080, 1920
        img = paint_bg((W, H), accent)
        d = ImageDraw.Draw(img)

        text(d, (84, 96), "Money Milestone", 30, "#64748B", True)
        ph = pill(d, 84, 150, tag, accent, size=27)
        multiline(d, 82, 150 + ph + 22, [title], 78, "#0F172A", True, max_width=940)
        text(d, (84, 150 + ph + 22 + 108), subtitle, 37, "#475569", False)
        text(d, (86, 150 + ph + 22 + 108 + 56), "예시 화면 · 정보 제공용", 24, "#94A3B8", False)

        floating_frame(img, RAW / raw_name, 195, 486, 690, 1372, radius=78, bezel=20)
        img.convert("RGB").save(OUT / f"phone-{key}.png", quality=95)


TABLET_SPECS = [
    ("01-home", "홈", "자산배분 포트폴리오", "내 자산과 수익률을 한눈에", "01-home.png", "#F97316"),
    ("02-holdings", "내 자산", "주식·ETF·금·채권", "국내외 인기 자산을 함께 관리", "03-holdings.png", "#059669"),
    ("03-rebalance", "리밸런싱", "목표 비중 리밸런싱", "흔들린 자산군을 바로 확인", "04-rebalance.png", "#4F46E5"),
    ("04-backtest", "백테스트", "전략은 백테스트로", "과거 데이터로 먼저 점검", "05-backtest.png", "#0EA5E9"),
]


def compose_tablet(prefix, size, frame):
    W, H = size
    fx, fy, fw, fh = frame
    s = W / 1080
    for key, tag, title, subtitle, suffix, accent in TABLET_SPECS:
        img = paint_bg(size, accent)
        d = ImageDraw.Draw(img)
        text(d, (int(80 * s), int(84 * s)), "Money Milestone", int(28 * s), "#64748B", True)
        ph = pill(d, int(80 * s), int(136 * s), tag, accent, size=int(25 * s))
        multiline(d, int(78 * s), int(136 * s) + ph + int(18 * s), [title], int(64 * s),
                  "#0F172A", True, max_width=int(W * 0.84))
        text(d, (int(80 * s), int(136 * s) + ph + int(18 * s) + int(92 * s)), subtitle,
             int(31 * s), "#475569", False)
        floating_frame(img, RAW / f"{prefix}-{suffix}", fx, fy, fw, fh,
                       radius=int(60 * s), bezel=max(16, int(18 * s)),
                       blur=int(46 * s), dy=int(34 * s))
        img.convert("RGB").save(OUT / f"{prefix}-{key}.png", quality=95)


def compose_feature():
    W, H, accent = 1024, 500, "#F97316"
    img = paint_bg((W, H), accent)
    d = ImageDraw.Draw(img)

    icon = Image.open(ICON).convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
    img.alpha_composite(icon, (66, 54))
    text(d, (152, 62), "Money Milestone", 28, "#334155", True)
    pill(d, 68, 116, "자산배분 투자 동반자", accent, size=22)
    multiline(d, 66, 178, ["내 자산·백테스트를", "한 화면에서"], 56, "#0F172A", True, spacing=6)

    chip_font = font(19, True)
    cx = 68
    for label, col in [("SPY 25%", "#2563EB"), ("TLT 10%", "#7C3AED"), ("KRX 금 5%", "#D97706")]:
        tw = int(d.textlength(label, font=chip_font)) + 34
        d.rounded_rectangle((cx, 372, cx + tw, 414), radius=21, fill=col)
        d.text((cx + 17, 379), label, font=chip_font, fill="#FFFFFF")
        cx += tw + 12

    floating_frame(img, RAW / "phone-02-assets.png", 648, 40, 214, 452,
                   radius=40, bezel=12, blur=30, shadow_alpha=70, dy=20)
    floating_frame(img, RAW / "phone-04-rebalance.png", 812, 86, 188, 384,
                   radius=36, bezel=11, blur=24, shadow_alpha=58, dy=16)
    img.convert("RGB").save(OUT / "feature-graphic-1024x500.png", quality=95)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON, OUT / "app-icon-512.png")
    compose_phone()
    compose_tablet("tablet7", (1200, 1920), (150, 520, 900, 1170))
    compose_tablet("tablet10", (1600, 2560), (190, 690, 1220, 1590))
    compose_feature()


if __name__ == "__main__":
    main()
