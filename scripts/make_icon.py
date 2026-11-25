"""Draw the brand icon: a street with a broom.

Usage: python scripts/make_icon.py custom_components/cambridge_street_sweeping/brand
"""

import math
import sys

from PIL import Image, ImageDraw

SS = 4  # supersampling factor


def draw(size: int) -> Image.Image:
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = S / 100  # 100-unit design grid

    # Rounded-square badge, city blue
    d.rounded_rectangle([2 * u, 2 * u, 98 * u, 98 * u], radius=22 * u, fill=(18, 74, 140))

    # Road running bottom-left to top-right, as a polygon band
    road = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(road)
    rd.rectangle([-30 * u, 36 * u, 130 * u, 72 * u], fill=(52, 58, 66))
    # curb lines
    rd.rectangle([-30 * u, 36 * u, 130 * u, 39 * u], fill=(200, 205, 212))
    rd.rectangle([-30 * u, 69 * u, 130 * u, 72 * u], fill=(200, 205, 212))
    # dashed centre line
    x = -30
    while x < 130:
        rd.rectangle([x * u, 52.5 * u, (x + 10) * u, 55.5 * u], fill=(255, 205, 40))
        x += 18
    road = road.rotate(18, resample=Image.BICUBIC, center=(S / 2, S / 2))
    # clip road to badge
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([2 * u, 2 * u, 98 * u, 98 * u], radius=22 * u, fill=255)
    road_alpha = Image.composite(road, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask)
    img = Image.alpha_composite(img, road_alpha)
    d = ImageDraw.Draw(img)

    # Broom: handle from top-left-ish to bristles resting on the road
    hx0, hy0 = 30 * u, 10 * u  # handle top
    hx1, hy1 = 60 * u, 60 * u  # handle bottom (ferrule)
    d.line([(hx0, hy0), (hx1, hy1)], fill=(150, 92, 45), width=int(6 * u))
    d.ellipse([hx0 - 3 * u, hy0 - 3 * u, hx0 + 3 * u, hy0 + 3 * u], fill=(150, 92, 45))

    # Bristle head: trapezoid perpendicular to the handle
    dx, dy = hx1 - hx0, hy1 - hy0
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L  # along handle
    px, py = -uy, ux  # perpendicular

    def pt(a, b):
        return (hx1 + ux * a * u + px * b * u, hy1 + uy * a * u + py * b * u)

    # ferrule band
    d.polygon([pt(-2, -7), pt(-2, 7), pt(4, 8), pt(4, -8)], fill=(255, 140, 26))
    # bristles fan
    bristles = [pt(4, -9), pt(4, 9), pt(24, 15), pt(24, -15)]
    d.polygon(bristles, fill=(255, 205, 40))
    for i in range(-13, 14, 4):
        a0 = pt(6, i * 0.6)
        a1 = pt(24, i)
        d.line([a0, a1], fill=(214, 150, 20), width=int(1.4 * u))

    # dust puffs swept off to the side
    for cx, cy, r in [(84, 78, 4.5), (90, 68, 3), (78, 88, 3)]:
        d.ellipse(
            [(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], fill=(235, 240, 245, 230)
        )

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1]
    draw(256).save(f"{out}/icon.png", optimize=True)
    draw(512).save(f"{out}/icon@2x.png", optimize=True)
