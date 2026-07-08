import struct, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hcs_tool import parse_tree, parse_body


def export_csv(in_path, out_path):
    data = Path(in_path).read_bytes()
    nodes = parse_tree(data, 8)

    prev_cmd = ''
    rows = []
    for n in nodes:
        if n[0] != 'CMD':
            prev_cmd = ''
            continue
        name = n[1]
        if name not in ('P', 'SR'):
            prev_cmd = name
            continue

        fields = parse_body(n[3])
        body_start = n[4] + 5 + len(name.encode('cp932'))
        bp = 0
        for typ, val in fields:
            if typ == 'str':
                offset = body_start + bp + 3
                orig_sjis = val.encode('cp932')
                spk = ''
                if '\u300c' in val or '\u300d' in val:
                    spk = prev_cmd
                rows.append({
                    'offset': f'0x{offset:08X}',
                    'length': str(len(orig_sjis)),
                    'type': name,
                    'name': spk,
                    'text': val,
                    'translation': '',
                })
                bp += 3 + len(orig_sjis)
            elif typ == 'end':
                bp += 2
            elif typ == 'hex':
                bp += len(val.split())
            elif typ in ('u32', 'sub'):
                bp += 6
            elif typ == 'ref':
                bp += 10
            elif typ == 'ref2':
                bp += 9
            elif typ == 'u16':
                bp += 3
            elif typ == 'u8':
                bp += 2

    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['offset', 'length', 'type', 'name', 'text', 'translation'])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def import_csv(in_path, csv_path, out_path):
    data = bytearray(Path(in_path).read_bytes())

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            t = row.get('translation', '').strip()
            if not t:
                continue
            offset = int(row['offset'], 16)
            max_len = int(row['length'])

            new_sjis = t.encode('cp932')
            if len(new_sjis) > max_len:
                print(f"ERROR: text too long at 0x{offset:08X}")
                print(f"  max={max_len} bytes, new={len(new_sjis)} bytes")
                print(f"  text: {t[:40]}")
                return

            data[offset:offset + len(new_sjis)] = new_sjis
            for i in range(len(new_sjis), max_len):
                data[offset + i] = 0

    Path(out_path).write_bytes(bytes(data))
    return len(data)


def main():
    import argparse
    p = argparse.ArgumentParser(prog='script_tool')
    subs = p.add_subparsers(dest='cmd')

    ex = subs.add_parser('export')
    ex.add_argument('-i', '--input', required=True)
    ex.add_argument('-o', '--output', required=True)

    im = subs.add_parser('import')
    im.add_argument('-i', '--input', required=True)
    im.add_argument('-c', '--csv', required=True)
    im.add_argument('-o', '--output', required=True)

    args = p.parse_args()

    if args.cmd == 'export':
        n = export_csv(args.input, args.output)
        print(f"export: {n} rows -> {args.output}")

    elif args.cmd == 'import':
        size = import_csv(args.input, args.csv, args.output)
        if size:
            print(f"import: {size:,}B -> {args.output}")
    
    else:
        p.print_help()


if __name__ == '__main__':
    main()
