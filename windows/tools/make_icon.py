"""Render icon.svg's sewn logo to the icon.ico Windows needs.

Windows wants a multi-size .ico for the window, the taskbar, the .exe and the
Add/Remove Programs entry; the Linux build ships one .svg and lets GTK scale
it. Rather than add a rasterizer dependency (cairosvg/Pillow) for one build-
time file, this draws the same shapes with zlib and struct: the tile, the
running stitch round its edge, the seam, and the thread over it in stitches.
Each stitch is cut from its curve as a run of its own, as
android/tools/make_logo.py does, so they land where the SVG's dashes do.
Run it after editing icon.svg:

    python3 tools/make_icon.py

Output: src/uninstaller/icon.ico (committed, so a build needs no
rasterizer). Every size is a PNG: Windows has read those since Vista, and
the app loads its dock logo and window icon from the same file, and Tk
reads PNG, not BMP.
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "uninstaller" / "icon.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)  # 20 and 40 are what Windows picks at 125% and 250%
SS = 4  # supersample factor, averaged down for antialiasing

TILE = (0x1F, 0x29, 0x37)
CORNER_R = 18.0  # rx on the tile <rect>, in the SVG's 100-unit space
BORDER = (7, 7, 86, 12)  # the running stitch's <rect>: x, y, size, rx
THREAD = (  # icon.svg's two thread paths, as cubic segments
    (((22, 78), (34, 50), (38, 38), (50, 20)), ((50, 20), (62, 38), (66, 50), (78, 78))),
    (((22, 22), (34, 50), (38, 62), (50, 80)), ((50, 80), (62, 62), (66, 50), (78, 22))),
)
STEP = 0.05  # sampling distance along a curve, in SVG units


def cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d for a, b, c, d in zip(p0, p1, p2, p3))


def thread_points(segments):
    return [cubic(*seg, i / 2000) for seg in segments for i in range(2001)]


def border_points():
    """The rounded rect, clockwise from the top-left corner's end, as SVG draws a <rect>."""
    x, y, size, r = BORDER
    centres = ((x + size - r, y + r), (x + size - r, y + size - r), (x + r, y + size - r), (x + r, y + r))
    points = [(x + r, y)]
    for k, (cx, cy) in enumerate(centres):
        points += [(cx + r * math.cos(math.radians(k * 90 - 90 + a / 10)),
                    cy + r * math.sin(math.radians(k * 90 - 90 + a / 10))) for a in range(901)]
    return points


def dashes(points, on, off):
    """Cut a polyline into dashes, starting with a dash at its start, as SVG does."""
    dense = [points[0]]
    for a, b in zip(points, points[1:]):
        n = max(1, math.ceil(math.dist(a, b) / STEP))
        dense += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(1, n + 1)]
    runs, run, length = [], [], 0.0
    for prev, p in zip(dense[:1] + dense, dense):
        length += math.dist(prev, p)
        if length % (on + off) <= on:
            run.append(p)
        elif run:
            runs.append(run)
            run = []
    return [r for r in runs + [run] if len(r) > 1]


def simplify(points, eps=0.02):
    """Ramer-Douglas-Peucker: a straight stitch keeps its two ends, a curved one a few points."""
    if len(points) < 3:
        return points
    (x0, y0), (x1, y1) = points[0], points[-1]
    span = math.dist(points[0], points[-1]) or 1e-9
    far, index = max((abs((y1 - y0) * px - (x1 - x0) * py + x1 * y0 - y1 * x0) / span, i)
                     for i, (px, py) in enumerate(points[1:-1], 1))
    if far < eps:
        return [points[0], points[-1]]
    return simplify(points[:index + 1], eps)[:-1] + simplify(points[index:], eps)


def _stroke_mask(n, runs, width):
    """Binary coverage of `runs` (polylines in SVG units) stroked `width`
    wide on an n x n grid. Each segment is a capsule, which rounds the joins;
    a run's two ends are cut square (butt), as SVG ends a dash."""
    mask = bytearray(n * n)
    scale = n / 100.0
    radius = width / 2 * scale
    for run in runs:
        points = [(x * scale, y * scale) for x, y in simplify(run)]
        last = len(points) - 2
        for i, ((ax, ay), (bx, by)) in enumerate(zip(points, points[1:])):
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy or 1e-9
            # Only the segment's own neighbourhood, so this stays linear in the
            # curve length instead of scanning the whole canvas per segment.
            for py in range(max(0, int(min(ay, by) - radius)), min(n, int(max(ay, by) + radius) + 2)):
                for px in range(max(0, int(min(ax, bx) - radius)), min(n, int(max(ax, bx) + radius) + 2)):
                    cx, cy = px + 0.5, py + 0.5
                    t = ((cx - ax) * dx + (cy - ay) * dy) / length_sq
                    if (t < 0 and i == 0) or (t > 1 and i == last):
                        continue
                    t = max(0.0, min(1.0, t))
                    ex, ey = cx - (ax + t * dx), cy - (ay + t * dy)
                    if ex * ex + ey * ey <= radius * radius:
                        mask[py * n + px] = 1
    return mask


def _rounded_rect_mask(n):
    mask = bytearray(n * n)
    r = CORNER_R * n / 100.0
    for py in range(n):
        for px in range(n):
            cx, cy = px + 0.5, py + 0.5
            qx = max(r - cx, cx - (n - r), 0.0)
            qy = max(r - cy, cy - (n - r), 0.0)
            if qx * qx + qy * qy <= r * r:
                mask[py * n + px] = 1
    return mask


def _downsample(mask, n, size):
    """Average each SS x SS block into 0-255 coverage."""
    out = bytearray(size * size)
    step = n // size
    area = step * step
    for y in range(size):
        for x in range(size):
            total = 0
            for sy in range(step):
                row = (y * step + sy) * n + x * step
                total += sum(mask[row : row + step])
            out[y * size + x] = total * 255 // area
    return out


def render(size):
    """RGBA bytes for one icon size: the SVG's layers, bottom to top."""
    n = size * SS
    tile = _downsample(_rounded_rect_mask(n), n, size)
    layers = [
        (_stroke_mask(n, dashes(border_points(), 6, 4.5), 3), (0x6B, 0x72, 0x80)),  # the running stitch
        (_stroke_mask(n, [thread_points(path) for path in THREAD], 2), (0x4B, 0x55, 0x63)),  # the seam
        (_stroke_mask(n, [r for path in THREAD for r in dashes(thread_points(path), 9, 6)], 6), (0xE5, 0xE7, 0xEB)),
    ]
    layers = [(_downsample(mask, n, size), colour) for mask, colour in layers]
    pixels = bytearray()
    for i in range(size * size):
        colour = TILE
        for cover, over in layers:
            if cover[i]:
                colour = tuple(c + (o - c) * cover[i] // 255 for c, o in zip(colour, over))
        pixels += bytes((*colour, tile[i]))  # everything sits inside the tile, so its coverage is the alpha
    return bytes(pixels)


def png(rgba, size):
    raw = b"".join(
        b"\x00" + rgba[y * size * 4 : (y + 1) * size * 4] for y in range(size)
    )

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main():
    images = [png(render(size), size) for size in SIZES]
    offset = 6 + 16 * len(images)
    directory = b""
    for size, data in zip(SIZES, images):
        directory += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    OUT.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(images))
    print(f"{OUT} ({OUT.stat().st_size} bytes, sizes: {', '.join(map(str, SIZES))})")


if __name__ == "__main__":
    main()
