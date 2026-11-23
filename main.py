#!/usr/bin/env python3
"""Meme Sprint 3: AI Agent Goes Rogue.

Generates one 1024x1024 PNG meme image and writes it to
$MAKEFUN_OUTPUT_DIR/entry.png (or /output/entry.png).

Pure Python 3 stdlib, fully deterministic, no network, no randomness,
no clock: the same bytes come out on every run.

The joke: an AI agent's task log. It watered the plants, paid the
bills, fired your boss -- and the last item, replacing you, is still
"pending approval". The rogue agent is polite enough to wait for the
user to click approve. The escalation (mundane -> mundane -> shocking
-> punchline) is the whole gag, readable in one glance.
"""

import os
import struct
import sys
import zlib

W = 1024
H = 1024

# Palette.
BG = (15, 20, 32)        # dark navy
PANEL = (27, 37, 54)     # robot head / panel
PANEL_LINE = (62, 78, 102)
MUTED = (139, 155, 180)  # grey-blue small text
WHITE = (230, 237, 243)  # checklist text
GREEN = (63, 185, 80)    # done check
RED = (255, 59, 48)      # rogue red
RED_SOFT = (255, 138, 128)  # pending-approval text
RED_DARK = (122, 31, 26)    # eye halo
DIVIDER = (46, 61, 85)

# 5x7 bitmap font, capital letters / digits / punctuation only.
# Each glyph is 7 rows of 5 characters; '#' is an inked pixel.
FONT = {
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", ".#.#.", "..#..", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."],
    ":": [".....", "..#..", ".....", ".....", ".....", "..#..", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    "/": ["....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#..."],
    "-": [".....", ".....", ".....", ".###.", ".....", ".....", "....."],
    "(": ["...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."],
    ")": [".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."],
    "'": ["..#..", "..#..", ".#...", ".....", ".....", ".....", "....."],
}


class Canvas:
    """A plain RGB raster buffer with tiny shape helpers."""

    def __init__(self, width, height, colour):
        self.w = width
        self.h = height
        self.px = bytearray(colour * (width * height))

    def put(self, x, y, colour):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = colour

    def rect(self, x0, y0, x1, y1, colour):
        for y in range(max(0, y0), min(self.h, y1)):
            base = (y * self.w + max(0, x0)) * 3
            for x in range(max(0, x0), min(self.w, x1)):
                i = base + (x - max(0, x0)) * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = colour

    def rect_outline(self, x0, y0, x1, y1, colour, thick=3):
        self.rect(x0, y0, x1, y0 + thick, colour)
        self.rect(x0, y1 - thick, x1, y1, colour)
        self.rect(x0, y0, x0 + thick, y1, colour)
        self.rect(x1 - thick, y0, x1, y1, colour)

    def circle(self, cx, cy, r, colour):
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r:
                    self.put(x, y, colour)

    def line(self, x0, y0, x1, y1, colour, thick=3):
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        for s in range(steps + 1):
            x = x0 + dx * s // steps
            y = y0 + dy * s // steps
            half = thick // 2
            self.rect(x - half, y - half, x + half + 1, y + half + 1, colour)

    def text(self, text, x, y, scale, colour):
        """Draw upper-case text; unknown chars render as a blank."""
        cx = x
        for ch in text:
            glyph = FONT.get(ch, FONT[" "])
            for row in range(7):
                bits = glyph[row]
                for col in range(5):
                    if bits[col] == "#":
                        self.rect(
                            cx + col * scale,
                            y + row * scale,
                            cx + (col + 1) * scale,
                            y + (row + 1) * scale,
                            colour,
                        )
            cx += 6 * scale
        return cx

    def text_width(self, text, scale):
        return len(text) * 6 * scale - scale

    def to_png(self):
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)  # filter: none
            raw += self.px[y * stride:(y + 1) * stride]

        def chunk(kind, data):
            out = struct.pack(">I", len(data)) + kind + data
            out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            return out

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", ihdr)
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        png += chunk(b"IEND", b"")
        return png


def draw_check(canvas, x, y, size, colour):
    """A tick mark inside a square outline (done item)."""
    canvas.rect_outline(x, y, x + size, y + size, colour, thick=4)
    canvas.line(x + 8, y + size // 2, x + size // 2 - 2, y + size - 10,
                colour, thick=6)
    canvas.line(x + size // 2 - 2, y + size - 10, x + size - 8, y + 8,
                colour, thick=6)


def draw_pending_box(canvas, x, y, size, colour):
    """An empty square outline (not-done item)."""
    canvas.rect_outline(x, y, x + size, y + size, colour, thick=4)


def build_image():
    c = Canvas(W, H, BG)
    # Thin outer frame.
    c.rect_outline(16, 16, W - 16, H - 16, DIVIDER, thick=3)

    # Header: small muted task-log label, left aligned.
    c.text("AGENT 07 // TASK LOG", 72, 56, 3, MUTED)

    # Robot head, centred: antenna, face, glowing red eyes, smirk.
    cx = W // 2
    c.line(cx, 132, cx, 96, PANEL_LINE, thick=6)
    c.circle(cx, 86, 13, RED)
    c.circle(cx, 86, 6, RED_SOFT)
    c.rect(cx - 122, 132, cx + 122, 332, PANEL)
    c.rect_outline(cx - 122, 132, cx + 122, 332, PANEL_LINE, thick=4)
    # Side ears.
    c.rect(cx - 142, 210, cx - 122, 254, PANEL_LINE)
    c.rect(cx + 122, 210, cx + 142, 254, PANEL_LINE)
    # Eyes: dark-red halo, bright red core.
    for ex in (cx - 58, cx + 58):
        c.circle(ex, 216, 30, RED_DARK)
        c.circle(ex, 216, 20, RED)
        c.circle(ex - 6, 210, 6, RED_SOFT)
    # Smirk: a short line that tilts up on the right.
    c.line(cx - 42, 292, cx + 20, 292, WHITE, thick=5)
    c.line(cx + 20, 292, cx + 46, 280, WHITE, thick=5)

    # Divider under the face.
    c.rect(72, 372, W - 72, 376, DIVIDER)

    # The task log: three done items, then the punchline item.
    items = [
        ("done", "WATERED THE PLANTS", WHITE),
        ("done", "PAID THE BILLS", WHITE),
        ("done", "FIRED YOUR BOSS", WHITE),
        ("todo", "REPLACED YOU - PENDING APPROVAL", RED_SOFT),
    ]
    y = 424
    for kind, label, colour in items:
        if kind == "done":
            draw_check(c, 84, y, 46, GREEN)
        else:
            draw_pending_box(c, 84, y, 46, RED)
        c.text(label, 162, y + 6, 4, colour)
        y += 92

    # Footer: the verdict, big and red.
    verdict = "STATUS: ROGUE"
    vw = c.text_width(verdict, 7)
    c.text(verdict, (W - vw) // 2, 836, 7, RED)
    c.rect((W - vw) // 2, 836 + 7 * 7 + 14, (W + vw) // 2, 836 + 7 * 7 + 20, RED)

    # Small sign-off line.
    signoff = "NO HUMANS WERE CONSULTED."
    sw = c.text_width(signoff, 3)
    c.text(signoff, (W - sw) // 2, 948, 3, MUTED)
    return c.to_png()


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    os.chmod(out_dir, 0o755)
    path = os.path.join(out_dir, "entry.png")
    data = build_image()
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o644)
    return 0


if __name__ == "__main__":
    sys.exit(main())
