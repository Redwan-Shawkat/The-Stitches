"""Render icon.svg's artwork to the icon.ico Windows needs.

Windows wants a multi-size .ico for the window, the taskbar, the .exe and the
Add/Remove Programs entry; the Linux build ships one .svg and lets GTK scale
it. Rather than add a rasterizer dependency (cairosvg/Pillow) for one build-
time file, this redraws the same two curves and the same rounded square with
zlib and struct — the shape is four cubic beziers, which is less code to
evaluate than a renderer is to install. Run it after editing icon.svg:

    python3 tools/make_icon.py

Output: src/uninstaller/icon.ico (committed, so a build needs no rasterizer).
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "uninstaller" / "icon.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 4  # supersample factor, averaged down for antialiasing

BG = (0x1F, 0x29, 0x37)
FG = (0xE5, 0xE7, 0xEB)
CORNER_R = 18.0  # rx on the <rect>, in the SVG's 100-unit space
STROKE_R = 3.5  # stroke-width 7 / 2
CURVES = (  # the two <path> d= values, as cubic segments
    ((22, 78), (34, 50), (38, 38), (50, 20)),
    ((50, 20), (62, 38), (66, 50), (78, 78)),
    ((22, 22), (34, 50), (38, 62), (50, 80)),
    ((50, 80), (62, 62), (66, 50), (78, 22)),
)


def polyline(steps=160):
    """The curves flattened to points, in SVG units."""
    lines = []
    for p0, p1, p2, p3 in CURVES:
        points = []
        for i in range(steps + 1):
            t, u = i / steps, 1 - i / steps
            points.append(
                (
                    u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                )
            )
        lines.extend(zip(points, points[1:]))
    return lines


def _stroke_mask(n):
    """Binary coverage of the two strokes on an n x n grid. Each segment is a
    capsule (distance to segment <= radius), which gives the round line caps
    and joins for free."""
    mask = bytearray(n * n)
    scale = n / 100.0
    radius = STROKE_R * scale
    for (x0, y0), (x1, y1) in polyline():
        ax, ay, bx, by = x0 * scale, y0 * scale, x1 * scale, y1 * scale
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy or 1e-9
        # Only the segment's own neighbourhood, so this stays linear in the
        # curve length instead of scanning the whole canvas per segment.
        for py in range(max(0, int(min(ay, by) - radius)), min(n, int(max(ay, by) + radius) + 2)):
            for px in range(
                max(0, int(min(ax, bx) - radius)), min(n, int(max(ax, bx) + radius) + 2)
            ):
                cx, cy = px + 0.5, py + 0.5
                t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / length_sq))
                ex, ey = cx - (ax + t * dx), cy - (ay + t * dy)
                if ex * ex + ey * ey <= radius * radius:
                    mask[py * n + px] = 1
    return mask


def _rounded_rect_mask(n):
    mask = bytearray(n * n)
    scale = n / 100.0
    r = CORNER_R * scale
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
    """RGBA bytes for one icon size."""
    n = size * SS
    bg = _downsample(_rounded_rect_mask(n), n, size)
    fg = _downsample(_stroke_mask(n), n, size)
    pixels = bytearray()
    for i in range(size * size):
        a, s = bg[i], fg[i]
        # Strokes sit inside the plate, so the plate's coverage is the alpha.
        pixels += bytes(
            (
                BG[0] + (FG[0] - BG[0]) * s // 255,
                BG[1] + (FG[1] - BG[1]) * s // 255,
                BG[2] + (FG[2] - BG[2]) * s // 255,
                a,
            )
        )
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


def dib(rgba, size):
    """A 32-bit bottom-up BMP without its file header, plus the AND mask —
    what an .ico entry holds for the non-PNG sizes."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for y in range(size - 1, -1, -1):
        row = rgba[y * size * 4 : (y + 1) * size * 4]
        rows.append(bytes(b for i in range(0, len(row), 4) for b in (row[i + 2], row[i + 1], row[i], row[i + 3])))
    mask_stride = ((size + 31) // 32) * 4
    return header + b"".join(rows) + b"\x00" * (mask_stride * size)


def main():
    images = []
    for size in SIZES:
        rgba = render(size)
        # PNG entries keep the 256px image from adding 256 KB to the file;
        # the small sizes stay as DIBs, which every Windows tool reads.
        images.append(png(rgba, size) if size >= 128 else dib(rgba, size))

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
