"""Render the Trackpad Free app icon into assets/ (PNG sizes plus a multi-size .ico).

Run after changing the design: python tools/make_icons.py
Standard library only; shapes are anti-aliased by supersampling.
"""

from __future__ import annotations

from pathlib import Path
import struct
import zlib

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
TOP, BOTTOM = (0x4C, 0x9D, 0xFF), (0x0A, 0x5A, 0xCF)
DOT = (0x0A, 0x64, 0xD6)


def inside_round_rect(u: float, v: float, x0: float, y0: float, x1: float, y1: float, radius: float) -> bool:
    dx = max(x0 + radius - u, 0.0, u - (x1 - radius))
    dy = max(y0 + radius - v, 0.0, v - (y1 - radius))
    return x0 <= u <= x1 and y0 <= v <= y1 and dx * dx + dy * dy <= radius * radius


def mix(base: tuple[float, ...], over: tuple[int, ...], amount: float) -> tuple[float, ...]:
    return tuple(b + (o - b) * amount for b, o in zip(base, over))


def icon_rgba(size: int) -> bytes:
    samples = 4 if size <= 64 else 3 if size <= 128 else 2
    count = samples * samples
    pixels = bytearray(size * size * 4)
    for y in range(size):
        t = y / max(size - 1, 1)
        base = tuple(a + (b - a) * t for a, b in zip(TOP, BOTTOM))
        for x in range(size):
            tile = pad = dots = 0
            for sy in range(samples):
                v = (y + (sy + 0.5) / samples) / size
                for sx in range(samples):
                    u = (x + (sx + 0.5) / samples) / size
                    tile += inside_round_rect(u, v, 0.03, 0.03, 0.97, 0.97, 0.22)
                    pad += inside_round_rect(u, v, 0.18, 0.27, 0.82, 0.73, 0.075)
                    dots += any((u - cx) ** 2 + (v - 0.5) ** 2 <= 0.058 ** 2 for cx in (0.415, 0.585))
            color = mix(mix(base, (255, 255, 255), pad / count), DOT, dots / count)
            index = (y * size + x) * 4
            pixels[index:index + 4] = bytes((*(round(channel) for channel in color), round(255 * tile / count)))
    return bytes(pixels)


def png(rgba: bytes, size: int) -> bytes:
    rows = b"".join(b"\0" + rgba[y * size * 4:(y + 1) * size * 4] for y in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def ico(images: dict[int, bytes]) -> bytes:
    """Windows icon file with PNG-compressed entries (supported since Windows Vista)."""
    offset = 6 + 16 * len(images)
    header, body = struct.pack("<HHH", 0, 1, len(images)), b""
    for size, data in sorted(images.items()):
        header += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(body))
        body += data
    return header + body


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    images = {}
    for size in SIZES:
        images[size] = png(icon_rgba(size), size)
        (ASSETS / f"icon-{size}.png").write_bytes(images[size])
    (ASSETS / "icon.ico").write_bytes(ico({size: images[size] for size in (16, 20, 24, 32, 40, 48, 64, 256)}))
    print(f"Wrote {len(SIZES)} PNG sizes and icon.ico to {ASSETS}")


if __name__ == "__main__":
    main()
