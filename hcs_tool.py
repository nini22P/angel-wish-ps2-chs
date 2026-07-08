import struct, sys
from pathlib import Path


def _dec_u32(data, off):
    if off + 5 >= len(data) or data[off] != 0x01 or data[off+1] != 0x01:
        return None
    return (struct.unpack_from('<I', data, off+2)[0], off+6)

def _enc_u32(v): return b'\x01\x01' + struct.pack('<I', int(v))

def _dec_u8(data, off):
    if off >= len(data) or data[off] != 0x0C: return None
    if off + 1 >= len(data): return None
    return (data[off+1], off+2)

def _enc_u8(v): return bytes([0x0C, int(v)])

def _dec_u16(data, off):
    if off >= len(data) or data[off] != 0x0F: return None
    if off + 2 >= len(data): return None
    return (struct.unpack_from('<H', data, off+1)[0], off+3)

def _enc_u16(v): return bytes([0x0F]) + struct.pack('<H', int(v))

def _dec_str(data, off):
    if off + 4 >= len(data) or data[off] != 0x01 or data[off+1] != 0x02:
        return None
    slen = data[off+2]
    if slen < 2 or off + slen + 3 > len(data): return None
    if data[off + 2 + slen] != 0x00: return None
    try:
        return (data[off+3:off+3+slen-1].decode('cp932'), off + slen + 3)
    except:
        return None

def _enc_str(v): return b'\x01\x02' + bytes([len(v.encode('cp932')) + 1]) + v.encode('cp932') + b'\x00'

def _dec_ref(data, off):
    if off + 9 >= len(data): return None
    if data[off] != 0x01 or data[off+1] != 0x03: return None
    if data[off+2] != 0x0E or data[off+3] != 0x01 or data[off+4] != 0x01 or data[off+5] != 0x01:
        return None
    return (data[off+6], off + 10)

def _enc_ref(v): return struct.pack('<BBBBBBBBBB', 0x01, 0x03, 0x0E, 0x01, 0x01, 0x01, int(v), 0, 0, 0)

def _dec_ref2(data, off):
    if off + 8 >= len(data) or data[off] != 0x0E: return None
    return ([struct.unpack_from('<I', data, off+1)[0], struct.unpack_from('<I', data, off+5)[0]], off + 9)

def _enc_ref2(v): return b'\x0E' + struct.pack('<II', v[0], v[1])

def _dec_sub(data, off):
    if off + 4 >= len(data) or data[off] != 0x0D: return None
    return (struct.unpack_from('<I', data, off+1)[0], off + 5)

def _enc_sub(v): return b'\x0D' + struct.pack('<I', int(v))

def _dec_end(data, off):
    if off + 1 >= len(data) or data[off] != 0x0B or data[off+1] != 0x00:
        return None
    return (True, off + 2)

def _enc_end(v): return b'\x0B\x00'

FIELD_TYPES = [
    ('str',  _dec_str,  _enc_str),
    ('ref',  _dec_ref,  _enc_ref),
    ('u32',  _dec_u32,  _enc_u32),
    ('sub',  _dec_sub,  _enc_sub),
    ('ref2', _dec_ref2, _enc_ref2),
    ('u16',  _dec_u16,  _enc_u16),
    ('u8',   _dec_u8,   _enc_u8),
    ('end',  _dec_end,  _enc_end),
]


def parse_body(body: bytes):
    fields = []
    off = 0
    while off < len(body):
        for name, decode_fn, _ in FIELD_TYPES:
            result = decode_fn(body, off)
            if result is not None:
                val, new_off = result
                fields.append((name, val))
                off = new_off
                break
        else:
            if fields and fields[-1][0] == 'hex':
                fields[-1] = ('hex', fields[-1][1] + f' {body[off]:02X}')
            else:
                fields.append(('hex', f'{body[off]:02X}'))
            off += 1
    return fields


def encode_body(fields):
    body = bytearray()
    for typ, val in fields:
        if typ == 'hex':
            for token in val.split():
                if len(token) >= 2:
                    try: body.append(int(token[:2], 16))
                    except ValueError: pass
        else:
            for name, _, encode_fn in FIELD_TYPES:
                if name == typ:
                    body.extend(encode_fn(val))
                    break
    return bytes(body)


def parse_command(data, pos):
    if pos + 5 > len(data) or data[pos] != 0x0A or data[pos+3] != 0x07:
        return None
    nlen = data[pos+4]
    if nlen < 1 or pos + 5 + nlen > len(data):
        return None
    try:
        name = data[pos+5:pos+5+nlen].decode('cp932')
    except:
        return None
    if any(ord(c) < 0x20 for c in name):
        return None

    body_start = pos + 5 + nlen
    body_end = body_start
    nest = 0
    while body_end < len(data):
        b = data[body_end]
        if b == 0x0A and body_end+3 < len(data) and data[body_end+3] == 0x07:
            if nest == 0: break
            nest += 1
            body_end += 5 + data[body_end+4]
        elif b == 0x0B and nest == 0:
            body_end += 2; break
        elif b == 0x0B:
            nest -= 1; body_end += 1
        else:
            body_end += 1

    raw = data[pos:body_end]
    body_bytes = raw[5 + raw[4]:]
    return name, raw[1], body_bytes, body_end


def parse_tree(data, start=8):
    nodes = []
    pos = start
    while pos < len(data):
        cmd_start = pos
        while cmd_start < len(data):
            if data[cmd_start] == 0x0A and cmd_start+4 < len(data) and data[cmd_start+3] == 0x07:
                break
            cmd_start += 1
        if cmd_start >= len(data):
            if pos < len(data):
                nodes.append(('DATA', pos, len(data[pos:]), data[pos:]))
            break
        if cmd_start > pos:
            nodes.append(('DATA', pos, cmd_start - pos, data[pos:cmd_start]))
        result = parse_command(data, cmd_start)
        if result is None:
            pos = cmd_start + 1; continue
        name, argc, body_bytes, end = result
        nodes.append(('CMD', name, argc, body_bytes, cmd_start))
        pos = end
    return nodes


def _rebuild_node(n):
    if n[0] == 'CMD':
        _, name, argc, body_bytes, old_off = n
        name_bytes = name.encode('cp932')
        cmd_head = struct.pack('<BBBBB', 0x0A, argc, 0x01, 0x07, len(name_bytes))
        return (old_off, cmd_head + name_bytes + body_bytes)
    else:
        _, old_off, size, raw = n
        return (old_off, raw)


def _quote(s: str) -> str:
    if any(c in s for c in ' ":#{}\n'):
        return '"' + s + '"'
    return s


def dump_text(header: bytes, nodes) -> str:
    lines = []
    lines.append('header: ' + header[:4].hex(' ') + '  ' + header[4:8].hex(' '))
    lines.append('')

    for node in nodes:
        if node[0] == 'CMD':
            _, name, argc, body_bytes, _ = node
            fields = parse_body(body_bytes)
            lines.append(_quote(name) + ' (argc=' + str(argc) + '):')
            for typ, val in fields:
                if typ in ('hex', 'str'):
                    lines.append('  ' + typ + ': "' + val + '"')
                elif typ == 'end':
                    lines.append('  end:')
                elif typ == 'ref2':
                    lines.append('  ' + typ + ': [' + str(val[0]) + ', ' + str(val[1]) + ']')
                else:
                    lines.append('  ' + typ + ': ' + str(val))
            lines.append('')
        else:
            _, offset, size, raw = node
            lines.append('data: 0x' + format(offset, '06X') + ' ' + str(size) + 'B')
            lines.append('  hex: "' + raw.hex(' ') + '"')
            lines.append('')
    return '\n'.join(lines)


def parse_text(text: str):
    lines = text.split('\n')
    header_bytes = b''
    nodes = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        if line.startswith('header:'):
            parts = line[7:].strip().split('  ')
            h0 = parts[0].replace(' ', '')
            h1 = parts[1].replace(' ', '')
            header_bytes = bytes.fromhex(h0) + bytes.fromhex(h1)
            i += 1; continue
        if line.startswith('#'):
            i += 1; continue

        if line.startswith('data:'):
            parts = line[5:].strip().split()
            offset = int(parts[0], 16)
            i += 1
            if i < len(lines) and 'hex:' in lines[i]:
                h = lines[i].strip()
                hex_str = h[h.find('"')+1:h.rfind('"')]
                raw = bytes.fromhex(hex_str.replace(' ', ''))
                nodes.append(('DATA', offset, len(raw), raw))
            i += 1; continue

        paren = line.rfind(' (argc=')
        if paren < 0: i += 1; continue

        name = line[:paren]
        if (name.startswith('"') and name.endswith('"')):
            name = name[1:-1]
        argc = int(line[paren+7:-2])

        fields = []
        i += 1
        while i < len(lines):
            bline = lines[i]
            if not bline.startswith('  '): break
            bline = bline.strip()
            if not bline: i += 1; continue
            colon = bline.find(':')
            if colon < 0: i += 1; continue
            typ = bline[:colon].strip()
            val = bline[colon+1:].strip()

            if typ in ('hex', 'str'):
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
            elif typ == 'end':
                val = True
            elif typ == 'ref2':
                if val.startswith('[') and val.endswith(']'):
                    parts = val[1:-1].split(',')
                    val = [int(parts[0].strip()), int(parts[1].strip())]
            elif typ in ('u32', 'u8', 'u16', 'ref', 'sub'):
                val = int(val)

            fields.append((typ, val))
            i += 1

        body = encode_body(fields)
        nodes.append(('CMD', name, argc, body))

    return header_bytes, nodes


def decode_cmd(in_path, out_path):
    data = Path(in_path).read_bytes()
    header = data[:8]
    nodes = parse_tree(data, 8)
    text = dump_text(header, nodes)
    if out_path:
        Path(out_path).write_text(text, encoding='utf-8')
    return text


def encode_cmd(in_path, out_path):
    text = Path(in_path).read_text(encoding='utf-8')
    header, nodes = parse_text(text)
    result = bytearray(header)
    for n in nodes:
        if n[0] == 'DATA':
            result.extend(n[3])
        elif n[0] == 'CMD':
            _, name, argc, body_bytes = n
            name_bytes = name.encode('cp932')
            cmd_head = struct.pack('<BBBBB', 0x0A, argc, 0x01, 0x07, len(name_bytes))
            cmd_head += name_bytes
            result.extend(cmd_head)
            result.extend(body_bytes)
    Path(out_path).write_bytes(bytes(result))
    return len(result)


def main():
    import argparse
    p = argparse.ArgumentParser(description='PS2 Angel Wish HCSList tool')
    subs = p.add_subparsers(dest='cmd')

    de = subs.add_parser('decode', help='bin -> txt')
    de.add_argument('-i', '--input', required=True)
    de.add_argument('-o', '--output', required=True)

    en = subs.add_parser('encode', help='txt -> bin')
    en.add_argument('-i', '--input', required=True)
    en.add_argument('-o', '--output', required=True)

    ts = subs.add_parser('test', help='roundtrip test')
    ts.add_argument('-i', '--input', required=True)

    args = p.parse_args()

    if args.cmd == 'decode':
        text = decode_cmd(args.input, args.output)
        print(f"decode: {text.count(chr(10))} lines -> {args.output}")

    elif args.cmd == 'encode':
        size = encode_cmd(args.input, args.output)
        print(f"encode: {size:,}B -> {args.output}")

    elif args.cmd == 'test':
        data = Path(args.input).read_bytes()
        nodes = parse_tree(data, 8)

        result = bytearray(data[:8])
        for n in nodes:
            old_off, raw = _rebuild_node(n)
            result.extend(raw)

        rebuilt = bytes(result)
        if rebuilt == data:
            print(f"test PASS: {len(data):,}B roundtrip identical")
        else:
            print(f"test FAIL: orig={len(data):,}B rebuilt={len(rebuilt):,}B")
            for i, (a, b) in enumerate(zip(data, rebuilt)):
                if a != b:
                    print(f"  first diff @ 0x{i:X}: orig=0x{a:02X} rebuilt=0x{b:02X}")
                    break


if __name__ == '__main__':
    main()
