#!/usr/bin/env python3
"""The World in One Picture -- Friday, 20 November 2026.

A program that draws one newspaper-style image summing up the world's news
of Friday 20 November 2026 and writes it to /output/entry.png.

Standard library only. No network, no randomness, no clock: run it twice
and the bytes are identical.

The picture: a front page with the date in the masthead and six stories
from that day, each with a drawn pictogram, a headline, a line of reporting
and its source. Every story below happened, or was first reported, on 20
November 2026 (in some time zone), and every claim on the page comes from
the source named beside it.

Text is rendered with bitmap fonts read from font.b64 beside this file:
DejaVu Sans Bold at 44 and 30 px and DejaVu Sans at 19 px, rasterized at
authoring time into 1-bit glyphs. The blob holds three faces in order
B44, B30, R19; for each, one byte of cell height (ascent + descent, so
every glyph shares one baseline), then characters 32..126 in order, each
stored as one width byte followed by row-major bits, most significant bit
first, 1 = ink.
"""

import base64
import math
import os
import struct
import zlib

_HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- fonts ---

_FACES = None
_GAP = (4, 3, 2)  # extra pixels between glyphs, per face


def _load_faces():
    global _FACES
    if _FACES is not None:
        return _FACES
    with open(os.path.join(_HERE, "font.b64"), "rb") as f:
        raw = zlib.decompress(base64.b64decode(f.read()))
    faces = []
    i = 0
    for _ in range(3):
        cell_h = raw[i]
        i += 1
        glyphs = []
        for _code in range(32, 127):
            w = raw[i]
            i += 1
            n = (w * cell_h + 7) // 8
            glyphs.append((w, cell_h, raw[i:i + n]))
            i += n
        faces.append(glyphs)
    _FACES = faces
    return faces


B44 = 0  # DejaVu Sans Bold, 44 px -- masthead date
B30 = 1  # DejaVu Sans Bold, 30 px -- headlines
R19 = 2  # DejaVu Sans, 19 px -- body, tags, sources


def text_width(s, face):
    glyphs = _load_faces()[face]
    w = 0
    for ch in s:
        code = ord(ch)
        if 32 <= code <= 126:
            w += glyphs[code - 32][0] + _GAP[face]
    return max(0, w - _GAP[face])


def wrap_text(s, face, max_w):
    """Greedy word wrap; returns a list of lines that fit max_w."""
    words = s.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, face) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ png ---

def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def save_png(path, width, height, rgb):
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        raw.extend(rgb[y * width * 3:(y + 1) * width * 3])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# --------------------------------------------------------------- sheet ---

PAPER = (248, 244, 236)
INK = (24, 32, 54)
CARD = (255, 253, 248)
MUTED = (96, 89, 74)
GOLD = (176, 141, 44)
CREAM = (250, 244, 228)
WHITE = (255, 255, 255)


class Sheet:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)
        self.box(0, 0, w, h, bg)

    def put(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = color

    def box(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + (x1 - x0) * 3] = row

    def frame(self, x, y, w, h, color, t=1):
        self.box(x, y, w, t, color)
        self.box(x, y + h - t, w, t, color)
        self.box(x, y, t, h, color)
        self.box(x + w - t, y, t, h, color)

    def hrule(self, x0, x1, y, color, t=1):
        self.box(x0, y, x1 - x0, t, color)

    def vrule(self, x, y0, y1, color, t=1):
        self.box(x, y0, t, y1 - y0, color)

    def seg(self, x0, y0, x1, y1, color, t=1):
        # Bresenham line, t pixels thick.
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = t // 2
        while True:
            for a in range(-half, half + 1):
                for b in range(-half, half + 1):
                    self.put(x0 + a, y0 + b, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def ball(self, cx, cy, r, color):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= r * r:
                    self.put(xx, yy, color)

    def loop(self, cx, cy, r, color, t=2):
        for yy in range(cy - r - 1, cy + r + 2):
            for xx in range(cx - r - 1, cx + r + 2):
                d2 = (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy)
                if (r - t) * (r - t) <= d2 <= r * r:
                    self.put(xx, yy, color)

    def polyfill(self, points, color):
        # Scanline fill for a simple polygon.
        ys = [p[1] for p in points]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            nodes = []
            n = len(points)
            for k in range(n):
                x0, y0 = points[k]
                x1, y1 = points[(k + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    nodes.append(int(x0 + (y - y0) * (x1 - x0) / (y1 - y0)))
            nodes.sort()
            for k in range(0, len(nodes) - 1, 2):
                for x in range(nodes[k], nodes[k + 1] + 1):
                    self.put(x, y, color)

    def burst(self, cx, cy, r, color, rays=10, t=3):
        for k in range(rays):
            ang = k * 2 * math.pi / rays
            self.seg(cx, cy,
                     cx + int(r * math.cos(ang)),
                     cy + int(r * math.sin(ang)), color, t)
        self.ball(cx, cy, max(3, r // 4), color)

    def glyph_at(self, x, y, glyph, color):
        w, h, bits = glyph
        for yy in range(h):
            for xx in range(w):
                bit = (bits[(yy * w + xx) // 8] >> (7 - (yy * w + xx) % 8)) & 1
                if bit:
                    self.put(x + xx, y + yy, color)

    def write(self, x, y, s, face, color):
        glyphs = _load_faces()[face]
        cx = x
        for ch in s:
            code = ord(ch)
            if 32 <= code <= 126:
                g = glyphs[code - 32]
                self.glyph_at(cx, y, g, color)
                cx += g[0] + _GAP[face]
        return cx - x

    def write_mid(self, cx, y, s, face, color):
        w = text_width(s, face)
        return self.write(cx - w // 2, y, s, face, color)


# -------------------------------------------------------------- pictograms ---

AMBER = (245, 158, 11)
PALE_GOLD = (253, 230, 138)
SKY = (147, 197, 253)
WAVE = (125, 211, 252)


def pic_kyiv(c, x, y, w, h):
    # Night skyline; the tallest tower is struck by a burst.
    base_y = y + h - 10
    heights = [36, 54, 46, 60, 42, 80, 68, 50]
    bw = w // 8
    for k, bh in enumerate(heights):
        bx = x + k * bw + 4
        c.box(bx, base_y - bh, bw - 8, bh, (16, 32, 64))
        for wy in range(base_y - bh + 8, base_y - 8, 12):
            for wx in (bx + 5, bx + bw - 14):
                c.box(wx, wy, 4, 5, PALE_GOLD)
    tx = x + 5 * bw + bw // 2
    c.burst(tx, base_y - 80 - 10, 16, AMBER, rays=8, t=3)
    for sx, sy in ((x + 30, y + 26), (x + w - 40, y + 20)):
        c.ball(sx, sy, 4, (200, 200, 200))
        c.ball(sx + 8, sy + 6, 3, (180, 180, 180))


def pic_cyclone(c, x, y, w, h):
    # A spiral storm with rain slashes at the edges.
    cx, cy = x + w // 2, y + h // 2 + 4
    prev = None
    steps = 90
    for k in range(steps + 1):
        ang = k * 4.4 * math.pi / steps
        r = 3 + 46 * k / steps
        px = cx + int(r * math.cos(ang))
        py = cy + int(r * math.sin(ang))
        if prev is not None:
            c.seg(prev[0], prev[1], px, py, WHITE, 3)
        prev = (px, py)
    c.ball(cx, cy, 6, (14, 116, 144))
    for sx in (x + 18, x + w - 26):
        for sy in (y + 22, y + 48, y + 74):
            c.seg(sx, sy, sx - 8, sy + 12, SKY, 2)


def pic_slump(c, x, y, w, h):
    # Bars falling away, with a downward arrow.
    base_y = y + h - 18
    bars = [88, 66, 44, 26]
    bw = 30
    gap = 14
    x0 = x + w // 2 - (4 * bw + 3 * gap) // 2
    for k, bh in enumerate(bars):
        bx = x0 + k * (bw + gap)
        c.box(bx, base_y - bh, bw, bh, CREAM)
    c.seg(x0 - 6, base_y - 92, x0 + 4 * bw + 3 * gap + 2,
          base_y - 30, AMBER, 5)
    tip_x = x0 + 4 * bw + 3 * gap + 2
    tip_y = base_y - 30
    # Arrowhead aligned with the line's own direction.
    dx = 4 * bw + 3 * gap + 8
    dy = 62
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n  # along the line
    px, py = -uy, ux  # perpendicular
    c.polyfill([(tip_x, tip_y),
                (tip_x - int(22 * ux) + int(9 * px),
                 tip_y - int(22 * uy) + int(9 * py)),
                (tip_x - int(22 * ux) - int(9 * px),
                 tip_y - int(22 * uy) - int(9 * py))], AMBER)
    c.hrule(x0 - 10, x0 + 4 * bw + 3 * gap + 10, base_y, CREAM, 3)


def pic_tanker(c, x, y, w, h):
    # A tanker at sea, burning at the bow.
    hull_y = y + 62
    c.polyfill([(x + 22, hull_y), (x + w - 22, hull_y),
                (x + w - 40, hull_y + 22), (x + 40, hull_y + 22)],
               (30, 41, 59))
    for k in range(4):
        bx = x + 48 + k * 52
        c.box(bx, hull_y - 22, 44, 22, (226, 232, 240) if k % 2 else (148, 163, 184))
    c.box(x + w - 84, hull_y - 34, 18, 34, WHITE)
    c.burst(x + w - 60, hull_y - 26, 15, AMBER, rays=8, t=3)
    for wy in (y + h - 20, y + h - 10):
        for wx in range(x + 16, x + w - 16, 24):
            c.hrule(wx, wx + 13, wy, WAVE, 2)


def pic_brake(c, x, y, w, h):
    # A rising line stopped flat by a red octagon.
    base_y = y + h - 20
    c.seg(x + 24, base_y - 78, x + w // 2 - 10, base_y - 40, CREAM, 5)
    c.seg(x + w // 2 - 10, base_y - 40, x + w - 30, base_y - 40, CREAM, 5)
    ox, oy, r = x + w - 62, y + 46, 30
    pts = []
    for k in range(8):
        ang = math.pi / 8 + k * math.pi / 4
        pts.append((ox + int(r * math.cos(ang)), oy + int(r * math.sin(ang))))
    c.polyfill(pts, (185, 28, 28))
    c.polyfill([(ox - 14, oy - 3), (ox + 14, oy - 3),
                (ox + 14, oy + 3), (ox - 14, oy + 3)], WHITE)
    c.hrule(x + 20, x + w - 20, base_y, CREAM, 3)


def pic_cricket(c, x, y, w, h):
    # Stumps, a bat and a red ball.
    cx = x + w // 2
    base_y = y + h - 16
    for sx in (cx - 52, cx - 42, cx - 32):
        c.vrule(sx, base_y - 44, base_y, CREAM, 4)
    c.hrule(cx - 54, cx - 28, base_y - 46, CREAM, 3)
    # Bat, leaning: thick blade, thin handle.
    c.seg(cx + 34, base_y - 6, cx + 62, base_y - 66, (222, 184, 135), 13)
    c.seg(cx + 62, base_y - 66, cx + 74, base_y - 92, (120, 84, 52), 5)
    c.ball(cx - 6, base_y - 78, 12, (185, 28, 28))
    c.loop(cx - 6, base_y - 78, 12, WHITE, 2)


PICS = {
    "kyiv": pic_kyiv,
    "cyclone": pic_cyclone,
    "slump": pic_slump,
    "tanker": pic_tanker,
    "brake": pic_brake,
    "cricket": pic_cricket,
}

# -------------------------------------------------------------- stories ---

NAVY = (31, 58, 95)
TEAL = (14, 116, 144)
CRIMSON = (153, 27, 27)
SLATE = (71, 85, 105)
FOREST = (22, 101, 52)
RUST = (146, 64, 14)

STORIES = [
    dict(tag="UKRAINE WAR", color=NAVY, pic="kyiv",
         head="Russia Strikes Kyiv Overnight",
         body="Missiles and drones hit homes and a bridge; fires burn in three districts.",
         src="SOURCE: REUTERS"),
    dict(tag="WEATHER", color=TEAL, pic="cyclone",
         head="Cyclone Akvan Hits Odisha Coast",
         body="Landfall near Gopalpur at noon; about 300,000 people moved to shelters.",
         src="SOURCE: THE HINDU"),
    dict(tag="MARKETS", color=CRIMSON, pic="slump",
         head="Asia Stocks in Worst Week Since 2020",
         body="AI-trade gloom deepens; the Nikkei falls 4.1% and the Kospi 4.7%.",
         src="SOURCE: REUTERS"),
    dict(tag="ENERGY", color=SLATE, pic="tanker",
         head="Another Tanker Burns Off Hormuz",
         body="Iran's navy says it hit a mine and caught fire; unconfirmed by others.",
         src="SOURCE: AL JAZEERA"),
    dict(tag="ASIA MARKETS", color=FOREST, pic="brake",
         head="Taiwan's Short-Selling Curbs Begin",
         body="Caps tighten to 1% after the Taiex's three-day, 5,000-point slide.",
         src="SOURCE: TAIWAN FSC"),
    dict(tag="SPORT", color=RUST, pic="cricket",
         head="New Zealand 243 for 5 on Day 1",
         body="Henry Nicholls' unbeaten century steadies the hosts in Wellington.",
         src="SOURCE: TIMES OF INDIA"),
]

W, H = 1024, 1024


def build():
    c = Sheet(W, H, PAPER)
    c.frame(12, 12, W - 24, H - 24, INK, 4)
    # Masthead.
    c.write_mid(W // 2, 34, "WORLD NEWS IN ONE PICTURE", R19, MUTED)
    c.write_mid(W // 2, 60, "FRIDAY, 20 NOVEMBER 2026", B44, INK)
    c.hrule(30, W - 30, 122, INK, 3)
    c.hrule(30, W - 30, 128, GOLD, 1)
    # Grid: 2 rows x 3 columns.
    gx, gy = 30, 142
    cw = 310
    ch = 391
    gap = 16
    for idx, s in enumerate(STORIES):
        row, col = divmod(idx, 3)
        x = gx + col * (cw + gap)
        y = gy + row * (ch + gap)
        c.box(x, y, cw, ch, CARD)
        c.frame(x, y, cw, ch, (216, 205, 184), 2)
        # Pictogram band.
        band_h = 116
        c.box(x + 2, y + 2, cw - 4, band_h, s["color"])
        PICS[s["pic"]](c, x + 2, y + 2, cw - 4, band_h)
        # Tag on a darker chip so the picture never crowds it.
        dark = tuple(max(0, v - 30) for v in s["color"])
        tag_w = text_width(s["tag"], R19)
        c.box(x + 10, y + 10, tag_w + 16, 28, dark)
        c.write(x + 18, y + 14, s["tag"], R19, WHITE)
        # Headline, up to 3 lines.
        ty = y + band_h + 14
        for line in wrap_text(s["head"], B30, cw - 28)[:3]:
            c.write(x + 14, ty, line, B30, INK)
            ty += 38
        # One line of reporting, up to 3 lines.
        ty += 6
        for line in wrap_text(s["body"], R19, cw - 28)[:3]:
            c.write(x + 14, ty, line, R19, (68, 64, 56))
            ty += 25
        # Source, pinned to the card's foot.
        c.write(x + 14, y + ch - 28, s["src"], R19, s["color"])
    # Footer.
    c.write_mid(
        W // 2, 950,
        "All events: Friday 20 November 2026",
        R19, MUTED)
    c.write_mid(
        W // 2, 976,
        "Sources: Reuters, The Hindu, Al Jazeera, Taiwan FSC, Times of India",
        R19, MUTED)
    return c


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    sheet = build()
    save_png(os.path.join(out_dir, "entry.png"), W, H, sheet.px)


if __name__ == "__main__":
    main()
