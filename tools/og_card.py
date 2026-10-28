"""Render 1200x630 Briefed share cards (Open Graph / iMessage) with Pillow."""
import os
from PIL import Image, ImageDraw, ImageFont

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "og-assets")
W, H = 1200, 630
NAVY, NAVY7, AMBER, WHITE, MUTED = "#041938", "#0B2A57", "#F79F1A", "#FFFFFF", "#AFC0D9"

def _f(name, size): return ImageFont.truetype(os.path.join(A, name), size)

def _wrap(d, text, font, width, max_lines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= width: cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while d.textlength(lines[-1] + "…", font=font) > width: lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines

def _base():
    im = Image.new("RGB", (W, H), NAVY); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=AMBER)
    logo = Image.open(os.path.join(A, "wordmark-white-transparent@2x.png")).convert("RGBA")
    logo = logo.resize((int(logo.width * 70 / logo.height), 70), Image.LANCZOS)
    im.paste(logo, (64, 52), logo)
    return im, d

def edition_card(path, date_label, headlines, footer):
    im, d = _base()
    d.text((W - 64, 74), date_label, font=_f("Inter-Bold.ttf", 34), fill=AMBER, anchor="ra")
    y = 170
    hf, sf = _f("Inter-ExtraBold.ttf", 52), _f("Inter-Bold.ttf", 34)
    for ln in _wrap(d, headlines[0], hf, W - 128, 3):
        d.text((64, y), ln, font=hf, fill=WHITE); y += 64
    y += 18
    for h in headlines[1:]:
        if y > H - 130: break
        d.ellipse([64, y + 13, 76, y + 25], fill=AMBER)
        d.text((92, y), _wrap(d, h, sf, W - 160, 1)[0], font=sf, fill=MUTED); y += 50
    d.rectangle([0, H - 72, W, H], fill=NAVY7)
    d.text((64, H - 36), footer, font=_f("Inter-Regular.ttf", 28), fill=WHITE, anchor="lm")
    d.text((W - 64, H - 36), "ljiindustries.com/briefed", font=_f("Inter-Bold.ttf", 28), fill=AMBER, anchor="rm")
    os.makedirs(os.path.dirname(path), exist_ok=True); im.save(path, optimize=True)

def generic_card(path):
    im, d = _base()
    d.text((64, 230), "The day's news. Just the facts,", font=_f("Inter-ExtraBold.ttf", 64), fill=WHITE)
    d.text((64, 310), "with links to the sources.", font=_f("Inter-ExtraBold.ttf", 64), fill=WHITE)
    d.text((64, 420), "A short daily edition you can read or listen to.", font=_f("Inter-Bold.ttf", 34), fill=MUTED)
    d.rectangle([0, H - 72, W, H], fill=NAVY7)
    d.text((64, H - 36), "Briefed by LJI Industries", font=_f("Inter-Regular.ttf", 28), fill=WHITE, anchor="lm")
    d.text((W - 64, H - 36), "ljiindustries.com/briefed", font=_f("Inter-Bold.ttf", 28), fill=AMBER, anchor="rm")
    os.makedirs(os.path.dirname(path), exist_ok=True); im.save(path, optimize=True)
