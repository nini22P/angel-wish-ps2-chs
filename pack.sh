#!/bin/sh

set -e

ROOT_DIR=$(pwd)

export PATH="$ROOT_DIR:$ROOT_DIR/bin:$PATH"

mkdir -p build build/SCRIPT build/GLOBAL

if [ ! -d raw/iso ]; then
    echo "Extracting ISO..."
    7z x "raw/Angel Wish - Kimi no Egao ni Chu! (Japan).iso" -oraw/iso
fi

if [ ! -f "build/Angel Wish - Kimi no Egao ni Chu! (Japan).iso" ]; then
    echo "Copying ISO to build directory..."
    cp -r "raw/Angel Wish - Kimi no Egao ni Chu! (Japan).iso" build/
fi

if [ ! -d raw/GLOBAL ]; then
    echo "Extracting GLOBAL.SAF..."
    python saf_tool.py unpack -i raw/iso/DATA/GLOBAL.SAF -o raw/GLOBAL
fi

if [ ! -d raw/SCRIPT ]; then
    echo "Extracting SCRIPT.SAF..."
    python saf_tool.py unpack -i raw/iso/DATA/SCRIPT.SAF -o raw/SCRIPT
fi

python mapping_tool.py

python script_tool.py import -i raw/SCRIPT/hcslist.bin -c build/script_mapped.csv -o build/SCRIPT/hcslist.bin

python draw_font_texture.py -i raw/GLOBAL/sce24i24.bin -f assets/NotoSansCJKsc-Medium.otf -m build/mapping.toml -o build/24x24.png --offset-y 8
python font_tool.py encode -i build/24x24.png -o build/GLOBAL/sce24i24.bin

python saf_tool.py replace -i raw/iso/DATA/SCRIPT.SAF -d build/SCRIPT -o build/SCRIPT.SAF
python saf_tool.py replace -i raw/iso/DATA/GLOBAL.SAF -d build/GLOBAL -o build/GLOBAL.SAF

if [ -d "assets/COMMON" ]; then
    python saf_tool.py replace -i raw/iso/DATA/COMMON.SAF -d assets/COMMON -o build/COMMON.SAF
fi

UMDReplaceK "build/Angel Wish - Kimi no Egao ni Chu! (Japan).iso" \
    DATA/SCRIPT.SAF build/SCRIPT.SAF \
    DATA/GLOBAL.SAF build/GLOBAL.SAF \
    DATA/COMMON.SAF build/COMMON.SAF \

echo "done"
