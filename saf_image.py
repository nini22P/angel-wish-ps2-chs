import struct
from pathlib import Path
from PIL import Image
from io import BytesIO
import pngquant_py


def unswizzle_palette(pal_bytes: bytes, bpp: int) -> bytes:
    if bpp == 32:
        new_pal = bytearray(1024)
        for p in range(256):
            pos = (p & 231) + ((p & 8) << 1) + ((p & 16) >> 1)
            for i in range(4):
                new_pal[pos * 4 + i] = pal_bytes[p * 4 + i]
        return bytes(new_pal)
    if bpp == 16:
        new_pal = bytearray(512)
        for p in range(256):
            pos = (p & 231) + ((p & 8) << 1) + ((p & 16) >> 1)
            for i in range(2):
                new_pal[pos * 2 + i] = pal_bytes[p * 2 + i]
        return bytes(new_pal)
    return pal_bytes


def unswizzle_palette_tm2(pal_buffer: bytes, nbpp: int) -> bytes:
    num_colors = len(pal_buffer) // nbpp
    pal = bytearray(len(pal_buffer))
    if num_colors > 256:
        banks = num_colors // 256
        for b in range(banks):
            for p in range(256):
                pos = (p & 231) + ((p & 8) << 1) + ((p & 16) >> 1)
                if pos < 256:
                    src = (b * 256 + p) * nbpp
                    dst = (b * 256 + pos) * nbpp
                    for i in range(nbpp):
                        pal[dst + i] = pal_buffer[src + i]
    else:
        for p in range(num_colors):
            pos = (p & 231) + ((p & 8) << 1) + ((p & 16) >> 1)
            if pos < num_colors:
                for i in range(nbpp):
                    pal[pos * nbpp + i] = pal_buffer[p * nbpp + i]
    return bytes(pal)


def swizzle_palette(pal_bytes: bytes, bpp: int) -> bytes:
    if bpp == 32:
        sw = bytearray(1024)
        for p in range(256):
            pos = (p & 231) + ((p & 8) << 1) + ((p & 16) >> 1)
            for i in range(4):
                sw[p * 4 + i] = pal_bytes[pos * 4 + i]
        return bytes(sw)
    if bpp == 16:
        sw = bytearray(512)
        for p in range(256):
            pos = (p & 231) + ((p & 8) << 1) + ((p & 16) >> 1)
            for i in range(2):
                sw[p * 2 + i] = pal_bytes[pos * 2 + i]
        return bytes(sw)
    return pal_bytes


def decode_t2(data: bytes):
    from PIL import Image

    img_bpp_type = data[2]
    img_type = data[3]
    image_width = struct.unpack('<H', data[0xC:0xE])[0] & 0xFFF
    image_height = struct.unpack('<H', data[0xE:0x10])[0] & 0xFFF

    palette_size = 0x400 if (img_bpp_type & 1) else 0x40

    raw_pal = data[0x10:0x10 + palette_size]
    if img_type == 0x13:
        raw_pal = unswizzle_palette(raw_pal, 32)

    palette = bytearray(raw_pal)
    if img_type in (0x13, 0x14):
        for i in range(3, len(palette), 4):
            palette[i] = min(255, int((palette[i] / 128.0) * 255.0))

    pixel_data = data[0x10 + palette_size:]
    img = Image.new('RGBA', (image_width, image_height))

    if img_type in (0x13, 2):
        for y in range(image_height):
            for x in range(image_width):
                off = pixel_data[x + y * image_width] * 4
                img.putpixel((x, y), (palette[off], palette[off+1], palette[off+2], palette[off+3]))
    elif img_type == 0x14:
        row_bytes = (image_width + 1) >> 1
        for y in range(image_height):
            for x in range(image_width):
                b = pixel_data[(x >> 1) + y * row_bytes]
                idx = (b >> 4) & 0xF if (x & 1) else b & 0xF
                off = idx * 4
                img.putpixel((x, y), (palette[off], palette[off+1], palette[off+2], palette[off+3]))

    return img


def decode_tim2(data: bytes):
    from PIL import Image

    if data[:4] != b'TIM2':
        raise ValueError("not a valid TIM2 file")

    version = data[5]
    picture_count = struct.unpack('<H', data[6:8])[0]
    images = []
    pic_offset = 0x10

    for _ in range(picture_count):
        if version == 1:
            pic_offset += 0x70

        total_size   = struct.unpack('<I', data[pic_offset:pic_offset+4])[0]
        clut_size    = struct.unpack('<I', data[pic_offset+4:pic_offset+8])[0]
        img_size_val = struct.unpack('<I', data[pic_offset+8:pic_offset+12])[0]
        header_size  = struct.unpack('<H', data[pic_offset+12:pic_offset+14])[0]
        clut_colors  = struct.unpack('<H', data[pic_offset+14:pic_offset+16])[0]
        clut_ct      = data[pic_offset + 0x12]
        img_ct       = data[pic_offset + 0x13]
        width        = struct.unpack('<H', data[pic_offset+0x14:pic_offset+0x16])[0]
        height       = struct.unpack('<H', data[pic_offset+0x16:pic_offset+0x18])[0]

        img_data_off = pic_offset + header_size
        clut_data_off = img_data_off + img_size_val

        palette = []
        if clut_size > 0:
            pal_bytes = bytearray(data[clut_data_off:clut_data_off + clut_size])
            if (clut_ct & 128) == 0 and clut_colors in (256, 512):
                nbpp = 2 if clut_size == clut_colors * 2 else 4
                pal_bytes = bytearray(unswizzle_palette_tm2(bytes(pal_bytes), nbpp))

            if clut_size == clut_colors * 4:
                for j in range(3, len(pal_bytes), 4):
                    pal_bytes[j] = min(255, int((pal_bytes[j] / 128.0) * 255.0))

            if clut_size == clut_colors * 2:
                for i in range(clut_colors):
                    px = struct.unpack('<H', pal_bytes[i*2:i*2+2])[0]
                    r = ((px & 0x1F) << 3) | ((px & 0x1F) >> 2)
                    g = (((px >> 5) & 0x1F) << 3) | (((px >> 5) & 0x1F) >> 2)
                    b = (((px >> 10) & 0x1F) << 3) | (((px >> 10) & 0x1F) >> 2)
                    a = 255 if (px >> 15) & 1 else 0
                    palette.append((r, g, b, a))
            elif clut_size == clut_colors * 4:
                for i in range(clut_colors):
                    palette.append((pal_bytes[i*4], pal_bytes[i*4+1], pal_bytes[i*4+2], pal_bytes[i*4+3]))

        def mki(w, h):
            return Image.new('RGBA', (w, h))

        if img_ct == 1:
            img = mki(width, height)
            for y in range(height):
                for x in range(width):
                    off = img_data_off + (y * width + x) * 2
                    px = struct.unpack('<H', data[off:off+2])[0]
                    r = ((px & 0x1F) << 3) | ((px & 0x1F) >> 2)
                    g = (((px >> 5) & 0x1F) << 3) | (((px >> 5) & 0x1F) >> 2)
                    b = (((px >> 10) & 0x1F) << 3) | (((px >> 10) & 0x1F) >> 2)
                    a = 255 if (px >> 15) & 1 else 0
                    img.putpixel((x, y), (r, g, b, a))
            images.append(img)

        elif img_ct == 2:
            img = mki(width, height)
            for y in range(height):
                for x in range(width):
                    off = img_data_off + (y * width + x) * 3
                    img.putpixel((x, y), (data[off], data[off+1], data[off+2], 255))
            images.append(img)

        elif img_ct == 3:
            img = mki(width, height)
            for y in range(height):
                for x in range(width):
                    off = img_data_off + (y * width + x) * 4
                    col = struct.unpack('<I', data[off:off+4])[0]
                    r, g, b = col & 0xFF, (col >> 8) & 0xFF, (col >> 16) & 0xFF
                    a = min(255, int(((col >> 24) & 0xFF) / 128.0 * 255.0))
                    img.putpixel((x, y), (r, g, b, a))
            images.append(img)

        elif img_ct == 4:
            img = mki(width, height)
            for y in range(height):
                for x in range(width):
                    b_val = data[img_data_off + ((y * width + x) >> 1)]
                    idx = b_val & 0xF if (x & 1) == 0 else (b_val >> 4) & 0xF
                    img.putpixel((x, y), palette[idx] if idx < len(palette) else (0, 0, 0, 255))
            images.append(img)

        elif img_ct == 5:
            if clut_colors > 256:
                banks = clut_colors // 256
                for bank in range(banks):
                    bank_img = mki(width, height)
                    bo = bank * 256
                    for y in range(height):
                        for x in range(width):
                            idx = data[img_data_off + y * width + x]
                            pi = bo + idx
                            bank_img.putpixel((x, y), palette[pi] if pi < len(palette) else (0, 0, 0, 255))
                    images.append(bank_img)
            else:
                img = mki(width, height)
                for y in range(height):
                    for x in range(width):
                        idx = data[img_data_off + y * width + x]
                        img.putpixel((x, y), palette[idx] if idx < len(palette) else (0, 0, 0, 255))
                images.append(img)

        pic_offset += total_size
    return images


def png_to_t2(png_path: str, orig_t2_header: bytes) -> bytes:
    img_bpp_type = orig_t2_header[2]
    img_type = orig_t2_header[3]
    orig_w = struct.unpack('<H', orig_t2_header[0xC:0xE])[0] & 0xFFF
    orig_h = struct.unpack('<H', orig_t2_header[0xE:0x10])[0] & 0xFFF

    img = Image.open(png_path).convert('RGBA')
    if img.size != (orig_w, orig_h):
        raise ValueError(f"size mismatch: PNG {img.size[0]}x{img.size[1]}, T2 expects {orig_w}x{orig_h}")

    colors = 256

    buf = BytesIO()
    img.save(buf, format='PNG')
    quantized_bytes = pngquant_py.quantize(buf.getvalue(), speed=1)
    q = Image.open(BytesIO(quantized_bytes))
    if q.mode != 'P':
        q = q.convert('P', palette=Image.Palette.ADAPTIVE, colors=colors)

    pal_rgb = q.getpalette() or [0] * (256 * 3)
    pal_rgb = [tuple(pal_rgb[i:i + 3]) for i in range(0, len(pal_rgb), 3)]
    while len(pal_rgb) < colors:
        pal_rgb.append((0, 0, 0))

    alpha_vals = [0xFF] * 256
    if 'transparency' in q.info:
        trans = q.info['transparency']
        if isinstance(trans, int):
            if trans < 256:
                alpha_vals[trans] = 0
        elif isinstance(trans, (bytes, bytearray, list)):
            for i, a in enumerate(trans):
                if i < 256:
                    alpha_vals[i] = a

    palette = bytearray()
    for i in range(colors):
        r, g, b = pal_rgb[i]
        a = alpha_vals[i] if i < len(alpha_vals) else 0xFF
        palette.extend([r, g, b, a])

    if img_type in (0x13, 0x14):
        for i in range(3, len(palette), 4):
            palette[i] = min(0xFF, int((palette[i] / 255.0) * 128.0))

    if img_type == 0x13:
        palette = bytearray(swizzle_palette(bytes(palette), 32))

    pix_data = q.tobytes()
    pixel_data = bytearray(orig_w * orig_h)
    n = min(len(pix_data), orig_w * orig_h)
    for y in range(orig_h):
        for x in range(orig_w):
            pos = y * orig_w + x
            pixel_data[pos] = pix_data[pos] if pos < n else 0

    t2 = struct.pack('<H', 0x3254)
    t2 += struct.pack('<BB', img_bpp_type, img_type)
    t2 += orig_t2_header[4:12]
    t2 += struct.pack('<HH', orig_w & 0xFFF, orig_h & 0xFFF)
    t2 += bytes(palette)
    t2 += bytes(pixel_data)
    return t2
