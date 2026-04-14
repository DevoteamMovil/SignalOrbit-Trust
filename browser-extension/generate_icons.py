"""
Generates PNG icons for the browser extension using Pillow (already installed).
Run: python browser-extension/generate_icons.py
"""

from PIL import Image, ImageDraw
import math
import os

SIZES = [16, 48, 128]
OUT_DIR = os.path.join(os.path.dirname(__file__), "icons")
os.makedirs(OUT_DIR, exist_ok=True)


def draw_icon(size: int) -> Image.Image:
    scale = size / 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background circle — dark purple gradient approximated as solid
    d.ellipse([0, 0, size - 1, size - 1], fill=(26, 10, 46, 255))

    cx, cy = size / 2, size / 2

    # Shield outline
    def shield_points(s):
        """Returns shield polygon points scaled to size s."""
        base = [
            (64, 18), (96, 32), (96, 64),
            (88, 78), (76, 90), (64, 104),
            (52, 90), (40, 78), (32, 64),
            (32, 32),
        ]
        return [(x * s / 128, y * s / 128) for x, y in base]

    pts = shield_points(size)
    d.polygon(pts, fill=(45, 16, 96, 200), outline=(192, 132, 252, 255))

    # Central circle (signal dot)
    r = max(2, int(10 * scale))
    d.ellipse(
        [cx - r, cy - r - int(6 * scale), cx + r, cy + r - int(6 * scale)],
        outline=(192, 132, 252, 255),
        width=max(1, int(2.5 * scale)),
    )

    # Vertical line below circle
    lx = int(cx)
    ly_start = int(cy + r - int(6 * scale)) + max(1, int(2 * scale))
    ly_end = int(cy + int(16 * scale))
    if ly_end > ly_start:
        d.line([(lx, ly_start), (lx, ly_end)], fill=(192, 132, 252, 255), width=max(1, int(2.5 * scale)))

    # Orbit ellipse (rotated) — draw as arc approximation
    if size >= 48:
        orbit_color = (138, 43, 226, 120)
        steps = 60
        rx, ry = int(28 * scale), int(10 * scale)
        angle_deg = -30
        angle_rad = math.radians(angle_deg)
        points = []
        for i in range(steps + 1):
            t = 2 * math.pi * i / steps
            x = rx * math.cos(t)
            y = ry * math.sin(t)
            xr = x * math.cos(angle_rad) - y * math.sin(angle_rad) + cx
            yr = x * math.sin(angle_rad) + y * math.cos(angle_rad) + cy
            points.append((xr, yr))
        d.line(points, fill=orbit_color, width=max(1, int(1.5 * scale)))

    return img


for size in SIZES:
    icon = draw_icon(size)
    out_path = os.path.join(OUT_DIR, f"icon{size}.png")
    icon.save(out_path, "PNG")
    print(f"Generated {out_path}")

print("Done.")
