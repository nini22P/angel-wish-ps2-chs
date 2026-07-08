import csv
import os
import json
from typing import Dict, Set, Any

MAPPING_OUTPUT: str = 'build/mapping.toml'
CSV_CONFIGS: list[Dict[str, Any]] = [
    {
        'input': 'script.csv',
        'output': 'build/script_mapped.csv',
        'original_cols': ['text'],
        'translation_cols': ['translation']
    },
]

GRID_ROWS = 94
GRID_COLS = 94
KANJI_ROW_START = 15  # 亜
KANJI_ROW_END = 83    # 熙


def build_jis_inventory() -> Dict[str, int]:
    inventory: Dict[str, int] = {}
    sj1_range = list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0))
    sj2_range = list(range(0x40, 0x7F)) + list(range(0x80, 0xFC + 1))
    for sj1 in sj1_range:
        for sj2 in sj2_range:
            try:
                ch = bytes([sj1, sj2]).decode('cp932')
            except Exception:
                continue
            if sj1 < 0xA0:
                t1 = sj1 - 0x81
            else:
                t1 = sj1 - 0xE0 + 0x1F
            j1 = t1 * 2 + 0x21
            if sj2 < 0x9F:
                t2 = sj2 - 0x40 if sj2 < 0x7F else sj2 - 0x41
                j2 = t2 + 0x21
            else:
                t2 = sj2 - 0x9F
                j2 = t2 + 0x21
                j1 += 1
            r, c = j1 - 0x21, j2 - 0x21
            if 0 <= r < GRID_ROWS and 0 <= c < GRID_COLS:
                inventory[ch] = r * GRID_COLS + c
    print(f"SJIS inventory: {len(inventory)} chars ({GRID_ROWS}x{GRID_COLS} grid)")
    return inventory


def is_cjk_ideograph(char: str) -> bool:
    code_int = ord(char)
    return 0x4E00 <= code_int <= 0x9FFF


def main() -> None:
    font_inventory = build_jis_inventory()
    if not font_inventory:
        print("Failed to build font inventory.")
        return

    needed_chars: Set[str] = set()
    chars_in_csv: Set[str] = set()

    for config in CSV_CONFIGS:
        path = config['input']
        if not os.path.exists(path):
            print(f"CSV not found: {path}")
            continue

        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col in config['original_cols']:
                    val = row.get(col, '')
                    if val:
                        for c in val:
                            chars_in_csv.add(c)

                for col in config['translation_cols']:
                    val = row.get(col, '')
                    if val:
                        for c in val:
                            chars_in_csv.add(c)
                            if ord(c) >= 0x80 and c not in font_inventory:
                                needed_chars.add(c)

    potential_slots: list[str] = [
        c for c in font_inventory.keys()
        if is_cjk_ideograph(c) and c not in needed_chars
        and KANJI_ROW_START <= font_inventory[c] // GRID_COLS <= KANJI_ROW_END
    ]

    unused_slots: list[str] = [c for c in potential_slots if c not in chars_in_csv]
    low_priority_slots: list[str] = [c for c in potential_slots if c in chars_in_csv]

    unused_slots.sort(key=lambda x: font_inventory[x])
    low_priority_slots.sort(key=lambda x: font_inventory[x])

    final_candidates: list[str] = unused_slots + low_priority_slots
    missing_chars: list[str] = sorted(list(needed_chars))

    print(f"\nMissing characters to map: {len(missing_chars)}")
    print(f"Available slots: Unused({len(unused_slots)}), Low priority({len(low_priority_slots)})")

    if len(missing_chars) > len(final_candidates):
        print(f"Warning - Not enough slots! Missing: {len(missing_chars)}, Candidates: {len(final_candidates)}")
        missing_chars = missing_chars[:len(final_candidates)]

    final_mapping: Dict[str, str] = {}
    trans_table: Dict[int, str] = {}

    for i, cn_char in enumerate(missing_chars):
        slot_jp_char = final_candidates[i]
        final_mapping[slot_jp_char] = cn_char
        trans_table[ord(cn_char)] = slot_jp_char

    with open(MAPPING_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("# Generated Mapping Table\n[replace]\n")
        for jp_char, cn_char in final_mapping.items():
            k_s = json.dumps(jp_char, ensure_ascii=False)
            v_s = json.dumps(cn_char, ensure_ascii=False)
            f.write(f"{k_s} = {v_s}\n")
    print(f"Mapping saved: {MAPPING_OUTPUT}")

    for config in CSV_CONFIGS:
        path = config['input']
        out_path = config['output']
        if not os.path.exists(path):
            continue

        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)

        if fieldnames is None:
            print(f"Error: Could not read fieldnames from {path}")
            continue

        with open(out_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                for col in config['translation_cols']:
                    val = row.get(col, '')
                    if val:
                        row[col] = val.translate(trans_table)
                writer.writerow(row)
        print(f"Mapped CSV saved: {out_path}")

    print("\nCompleted!")


if __name__ == '__main__':
    main()
