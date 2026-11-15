#!/usr/bin/env python3
"""Regenerate icon.svg, favicon.ico (16/32/48) and favicon-32.png from the site's original inline SVG icon (dark rounded square, red bold $).
Run once; outputs are committed. Needs Pillow and a bold sans font (Liberation Sans Bold or DejaVu Sans Bold)."""
import os
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#07090d"/>'
       '<text x="16" y="23" font-size="20" text-anchor="middle" fill="#ff4d5e" font-family="Arial" font-weight="900">$</text></svg>\n')
FONTS = ["/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
def render(px, ss=8):
    n = px * ss; k = n / 32
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=6 * k, fill="#07090d")
    f = ImageFont.truetype(next(x for x in FONTS if os.path.exists(x)), int(20 * k))
    d.text((16 * k, 23 * k), "$", font=f, fill="#ff4d5e", anchor="ms")  # middle-x, baseline: same anchors as the SVG text
    return im.resize((px, px), Image.LANCZOS)
open(os.path.join(ROOT, "icon.svg"), "w").write(SVG)
big = render(256, 2)
big.save(os.path.join(ROOT, "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
render(32).save(os.path.join(ROOT, "favicon-32.png"))
print("wrote icon.svg favicon.ico favicon-32.png")
