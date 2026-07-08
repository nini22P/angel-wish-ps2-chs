import struct, zlib

MAGIC_SAF0 = 0x30464153
MAGIC_T2   = 0x3254
MAGIC_TIM2 = 0x324D4954


def decode_cp932(data: bytes) -> str:
    end = data.find(b'\x00')
    if end >= 0:
        data = data[:end]
    return data.decode('cp932', errors='replace')


def parse_saf(filepath):
    with open(filepath, 'rb') as f:
        magic = struct.unpack('<I', f.read(4))[0]
        if magic != MAGIC_SAF0:
            raise ValueError(f"not a SAF file (magic=0x{magic:08X})")

        version = struct.unpack('<I', f.read(4))[0]
        if version not in (1, 2):
            raise ValueError(f"unsupported SAF version: {version}")

        unk08 = struct.unpack('<I', f.read(4))[0]
        num_files = struct.unpack('<I', f.read(4))[0]

        entry_sz = 0x20 if version == 1 else 0x30
        name_sz  = 16   if version == 1 else 32

        files = []
        for i in range(num_files):
            f.seek(0x10 + i * entry_sz)
            _       = struct.unpack('<I', f.read(4))[0]
            f_offset = struct.unpack('<I', f.read(4))[0]
            f_size   = struct.unpack('<I', f.read(4))[0]
            dec_size = struct.unpack('<I', f.read(4))[0]
            name     = decode_cp932(f.read(name_sz))

            files.append({
                'name': name or f'file_{i:04d}',
                'offset': f_offset,
                'size': f_size,
                'dec_size': dec_size,
            })
        return version, unk08, files


def read_entry(filepath, entry) -> bytes:
    with open(filepath, 'rb') as f:
        f.seek(entry['offset'])
        data = f.read(entry['size'])
    if entry['size'] != entry['dec_size']:
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass
    return data


def load_file_list(filepath):
    version, unk08, files = parse_saf(filepath)
    for entry in files:
        data = read_entry(filepath, entry)
        if len(data) >= 2 and struct.unpack('<H', data[:2])[0] == MAGIC_T2:
            entry['ext'] = '.T2'
        elif len(data) >= 4 and struct.unpack('<I', data[:4])[0] == MAGIC_TIM2:
            entry['ext'] = '.TM2'
        elif len(data) >= 4 and struct.unpack('<I', data[:4])[0] == MAGIC_SAF0:
            entry['ext'] = '.saf'
        else:
            entry['ext'] = '.bin'
    return version, unk08, files
