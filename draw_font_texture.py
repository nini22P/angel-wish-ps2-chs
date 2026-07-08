import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from font_tool import (
    GRID_ROWS, GRID_COLS, CELL_SIZE,
    TOTAL_GLYPHS, PNG_W, PNG_H,
    load_font, glyph_to_image,
)
from mapping_tool import build_jis_inventory

DRAW_ROW_START = 0
DRAW_ROW_END = 83


def load_mapping(path):
    mapping = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if '=' in line and not line.startswith('#') and not line.startswith('['):
            k, v = line.split('=', 1)
            k = k.strip().strip('"')
            v = v.strip().strip('"')
            if k and v:
                mapping[k] = v
    return mapping


def dict_to_grid(inventory):
    grid: list[list[str | None]] = [[None] * GRID_COLS for _ in range(GRID_ROWS)]
    for ch, idx in inventory.items():
        r, c = divmod(idx, GRID_COLS)
        if 0 <= r < GRID_ROWS and 0 <= c < GRID_COLS:
            grid[r][c] = ch
    return grid


def draw_char(draw, font, ch, x, y, stroke_width=0, stroke_fill=None, offset_y=0):
    cx = x + CELL_SIZE / 2
    cy = y + CELL_SIZE / 2 + offset_y
    draw.text((cx, cy), ch, font=font, fill=(0, 0, 0, 255), anchor='ms', stroke_width=stroke_width, stroke_fill=stroke_fill)


def main():
    p = argparse.ArgumentParser(description='Draw font texture')
    p.add_argument('-i', '--input', required=True, help='original font .bin file')
    p.add_argument('-f', '--font', required=True, help='TTF/OTF font file')
    p.add_argument('-m', '--mapping', required=True, help='mapping.toml')
    p.add_argument('-o', '--output', required=True, help='output .png')
    p.add_argument('--size', type=float, default=22.0, help='font size (default: 22)')
    p.add_argument('--stroke-width', type=int, default=1, help='stroke width in pixels (default: 1)')
    p.add_argument('--stroke-color', default='0,0,0,64', help='stroke color R,G,B,A (default: 0,0,0,64)')
    p.add_argument('--offset-y', type=int, default=0, help='vertical offset in pixels (default: 0)')
    args = p.parse_args()

    stroke_fill = None
    if args.stroke_width > 0:
        parts = [int(x) for x in args.stroke_color.split(',')]
        if len(parts) == 3:
            r, g, b = parts
            a = 128
        else:
            r, g, b, a = parts
        stroke_fill = (r, g, b, a)

    data = load_font(args.input)
    mapping = load_mapping(args.mapping)
    grid = dict_to_grid(build_jis_inventory())

    font = ImageFont.truetype(args.font, args.size)

    img = Image.new('RGBA', (PNG_W, PNG_H), (0, 0, 0, 0))
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            glyph = glyph_to_image(Image, data, r * GRID_COLS + c)
            img.paste(glyph, (c * CELL_SIZE, r * CELL_SIZE))

    draw = ImageDraw.Draw(img)

    for r in range(DRAW_ROW_START, DRAW_ROW_END + 1):
        for c in range(GRID_COLS):
            x0, y0 = c * CELL_SIZE, r * CELL_SIZE
            draw.rectangle([x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE], fill=(0, 0, 0, 0))

    drawn = 0
    replaced = 0
    for r in range(DRAW_ROW_START, DRAW_ROW_END + 1):
        for c in range(GRID_COLS):
            ch = grid[r][c]
            if ch is None:
                continue
            x = c * CELL_SIZE
            y = r * CELL_SIZE
            if ch in mapping:
                draw_char(draw, font, mapping[ch], x, y, args.stroke_width, stroke_fill, args.offset_y)
                replaced += 1
            else:
                draw_char(draw, font, ch, x, y, args.stroke_width, stroke_fill, args.offset_y)
            drawn += 1

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    img.save(str(args.output))
    print(f"draw {drawn} glyphs ({replaced} replaced) rows {DRAW_ROW_START}-{DRAW_ROW_END} -> {args.output}")


if __name__ == '__main__':
    main()
