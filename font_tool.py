import struct
import sys
from pathlib import Path
from PIL import Image


GRID_COLS = 94
GRID_ROWS = 94
CELL_SIZE = 24
GLYPH_BYTES = CELL_SIZE * CELL_SIZE // 2
TOTAL_GLYPHS = GRID_COLS * GRID_ROWS
PNG_W = GRID_COLS * CELL_SIZE
PNG_H = GRID_ROWS * CELL_SIZE


def load_font(path):
    data = Path(path).read_bytes()
    expected = TOTAL_GLYPHS * GLYPH_BYTES
    if len(data) < expected:
        sys.exit(f"file too small: {len(data)} < {expected}")
    if len(data) > expected:
        print(f"warning: file has {len(data) - expected} extra bytes, ignoring")
    return data


def glyph_to_image(Image, data, idx):
    off = idx * GLYPH_BYTES
    img = Image.new('RGBA', (CELL_SIZE, CELL_SIZE), (0, 0, 0, 0))
    pixels = []
    for row in range(CELL_SIZE):
        for col in range(CELL_SIZE):
            b = data[off + row * (CELL_SIZE // 2) + col // 2]
            nib = b & 0x0F if col % 2 == 0 else (b >> 4) & 0x0F
            a = nib * 17
            pixels.append((0, 0, 0, a))
    img.putdata(pixels)
    return img


def decode(font_path, out_path):
    data = load_font(font_path)
    img = Image.new('RGBA', (PNG_W, PNG_H), (0, 0, 0, 0))

    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            glyph = glyph_to_image(Image, data, r * GRID_COLS + c)
            img.paste(glyph, (c * CELL_SIZE, r * CELL_SIZE))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path))
    print(f"{GRID_ROWS}x{GRID_COLS} grid -> {out_path} ({PNG_W}x{PNG_H})")


def image_to_glyph(Image, img, cell_x, cell_y):
    glyph = img.crop((cell_x * CELL_SIZE, cell_y * CELL_SIZE,
                      (cell_x + 1) * CELL_SIZE, (cell_y + 1) * CELL_SIZE))
    raw = glyph.tobytes()
    out = bytearray(GLYPH_BYTES)
    for i in range(CELL_SIZE * CELL_SIZE):
        a = raw[i * 4 + 3]
        nib = (a * 15 + 127) // 255
        byte_idx = i // 2
        if i % 2 == 0:
            out[byte_idx] |= nib & 0x0F
        else:
            out[byte_idx] |= (nib << 4) & 0xF0
    return bytes(out)


def encode(png_path, out_path):
    img = Image.open(str(png_path)).convert('RGBA')
    w, h = img.size

    if w != PNG_W or h != PNG_H:
        sys.exit(f"image size {w}x{h} != expected {PNG_W}x{PNG_H} ({GRID_COLS}x{GRID_ROWS} grid, {CELL_SIZE}px cells)")

    buf = bytearray()
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            buf.extend(image_to_glyph(Image, img, c, r))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(bytes(buf))
    print(f"{png_path} -> {out_path} ({len(buf):,} bytes, {TOTAL_GLYPHS} glyphs)")


def main():
    import argparse
    p = argparse.ArgumentParser(description='PS2 font tool')
    sub = p.add_subparsers(dest='cmd')

    pe = sub.add_parser('decode', help='binary to PNG')
    pe.add_argument('-i', '--input', required=True, help='font .bin file')
    pe.add_argument('-o', '--output', required=True, help='output .png')
    pe.add_argument('-s', '--scale', type=int, default=1, help='scale factor (default: 1)')

    pi = sub.add_parser('encode', help='PNG to binary')
    pi.add_argument('-i', '--input', required=True, help='input .png')
    pi.add_argument('-o', '--output', required=True, help='output .bin file')

    args = p.parse_args()
    
    match args.cmd:
        case None: p.print_help()
        case 'decode': decode(args.input, args.output)
        case 'encode': encode(args.input, args.output)


if __name__ == '__main__':
    main()
