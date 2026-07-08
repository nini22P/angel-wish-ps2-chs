import struct, zlib
from pathlib import Path

from saf_core import MAGIC_SAF0, parse_saf, load_file_list, read_entry


def save_raw(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def unpack(archive_f, entry, out_path, convert_images):
    data = read_entry(str(archive_f.name), entry)

    name = entry['name']
    safe_name = name.replace('/', '_').replace('\\', '_').replace(':', '_')
    out_path = out_path.parent / safe_name
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ext = entry.get('ext', '.bin')
    if ext == '.T2':
        if convert_images:
            try:
                from saf_image import decode_t2
                img = decode_t2(data)
                img.save(str(out_path.with_suffix('.png')))
                print(f"    [T2->PNG] {name}")
                return
            except Exception: pass
        save_raw(out_path.with_suffix('.T2'), data)
        print(f"    [T2] {name} ({len(data)} bytes)")

    elif ext == '.TM2':
        if convert_images:
            try:
                from saf_image import decode_tim2
                imgs = decode_tim2(data)
                stem = out_path.stem
                for idx, img in enumerate(imgs):
                    p = (out_path.with_suffix('.png') if len(imgs) == 1
                         else out_path.with_name(f"{stem}_{idx:04d}.png"))
                    img.save(str(p))
                print(f"    [TIM2->PNG] {name} ({len(imgs)} frames)")
                return
            except Exception: pass
        save_raw(out_path.with_suffix('.TM2'), data)
        print(f"    [TIM2] {name} ({len(data)} bytes)")

    elif ext == '.saf':
        save_raw(out_path.with_suffix('.saf'), data)
        print(f"    [nested SAF] {name} ({len(data)} bytes)")

    else:
        save_raw(out_path.with_suffix('.bin'), data)
        print(f"    [{name}] ({len(data)} bytes)")


def cmd_info(args):
    path = Path(args.input)
    version, unk08, files = parse_saf(path)
    print(f"file: {path}")
    print(f"size: {path.stat().st_size:,} bytes")
    print(f"version: {version}")
    print(f"files: {len(files)}")
    print(f"0x08 field: 0x{unk08:08X} ({unk08:,})")
    print(f"entry size: {0x20 if version == 1 else 0x30} bytes")
    print(f"name max: {16 if version == 1 else 32} chars")


def cmd_list(args):
    path = Path(args.input)
    _, _, files = load_file_list(str(path))
    print(f"{'Offset':>10}  {'Size':>10}  {'DecSize':>10}  Name")
    print("-" * 58)
    for e in files:
        print(f"0x{e['offset']:08X}  {e['size']:10,d}  {e['dec_size']:10,d}  {e['name']}{e['ext']}")


def cmd_unpack(args):
    path = Path(args.input)
    output_dir = Path(args.output)

    _, _, files = load_file_list(str(path))
    print(f"{path.name}: {len(files)} files")

    with open(path, 'rb') as f:
        for entry in files:
            safe_name = entry['name'].replace('/', '_').replace('\\', '_').replace(':', '_')
            unpack(f, entry, output_dir / safe_name, convert_images=not args.raw)

    print(f"done -> {output_dir}")


def cmd_replace(args):
    input_path = Path(args.input)
    dir_path = Path(args.dir)
    output_path = Path(args.output)

    version, unk08, files = parse_saf(input_path)

    with open(input_path, 'rb') as f:
        orig_data = f.read()

    dir_files = {}
    for fp in dir_path.rglob('*'):
        if fp.is_file():
            dir_files[fp.stem] = fp

    new_entries = []
    data_start = 0x10 + len(files) * (0x20 if version == 1 else 0x30)
    data_pos = data_start
    replaced = 0

    for entry in files:
        name = entry['name']
        new_data = None
        match = dir_files.get(name)

        if match:
            if match.suffix.lower() == '.png':
                orig_entry_data = orig_data[entry['offset']:entry['offset'] + entry['size']]
                if entry['size'] != entry['dec_size']:
                    try: orig_entry_data = zlib.decompress(orig_entry_data)
                    except zlib.error: pass
                if len(orig_entry_data) >= 0x10:
                    from saf_image import png_to_t2
                    new_data = png_to_t2(str(match), orig_entry_data[:0x10])
            else:
                new_data = match.read_bytes()

        if new_data is not None:
            dec_sz = len(new_data)
            if entry['size'] != entry['dec_size']:
                new_data = zlib.compress(new_data, 9)
            new_entries.append({'name': name, 'offset': data_pos,
                'size': len(new_data), 'dec_size': dec_sz, 'data': new_data})
            data_pos += len(new_data)
            replaced += 1
        else:
            sz = entry['size']
            stored = orig_data[entry['offset']:entry['offset'] + sz]
            new_entries.append({'name': name, 'offset': data_pos,
                'size': sz, 'dec_size': entry['dec_size'], 'data': stored})
            data_pos += sz

    entry_sz = 0x20 if version == 1 else 0x30
    name_sz  = 16   if version == 1 else 32

    table = bytearray()
    for i, e in enumerate(new_entries):
        orig_unk = struct.unpack_from('<I', orig_data, 0x10 + i * entry_sz)[0]
        table.extend(struct.pack('<I', orig_unk))
        table.extend(struct.pack('<I', e['offset']))
        table.extend(struct.pack('<I', e['size']))
        table.extend(struct.pack('<I', e['dec_size']))
        name_bytes = e['name'].encode('cp932')[:name_sz]
        table.extend(name_bytes.ljust(name_sz, b'\x00'))

    total_size = 0x10 + len(table) + sum(e['size'] for e in new_entries)

    with open(output_path, 'wb') as f:
        f.write(struct.pack('<I', MAGIC_SAF0))
        f.write(struct.pack('<I', version))
        f.write(struct.pack('<I', total_size))
        f.write(struct.pack('<I', len(files)))
        f.write(table)
        for e in new_entries:
            f.write(e['data'])

    print(f"replaced: {len(files)} entries, {replaced} replaced -> {output_path} ({total_size:,}B)")


def main():
    import argparse
    p = argparse.ArgumentParser(description='SAF archive tool')
    subs = p.add_subparsers(dest='cmd')

    pi = subs.add_parser('info', help='show header info')
    pi.add_argument('-i', '--input', required=True)

    pl = subs.add_parser('list', help='list file table')
    pl.add_argument('-i', '--input', required=True)

    pu = subs.add_parser('unpack', help='extract files')
    pu.add_argument('-i', '--input', required=True)
    pu.add_argument('-o', '--output', default='./out')
    pu.add_argument('--raw', action='store_true', help='do not convert images')

    rp = subs.add_parser('replace', help='replace files in SAF from directory')
    rp.add_argument('-i', '--input', required=True, help='original SAF file')
    rp.add_argument('-d', '--dir', required=True, help='directory with replacement files')
    rp.add_argument('-o', '--output', required=True, help='output SAF file')

    args = p.parse_args()
    match args.cmd:
        case None: p.print_help()
        case 'info':    cmd_info(args)
        case 'list':    cmd_list(args)
        case 'unpack':  cmd_unpack(args)
        case 'replace': cmd_replace(args)


if __name__ == '__main__':
    main()
