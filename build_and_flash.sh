#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
BUILD_DIR="$PROJECT_ROOT/build"
TARGET="main"

HEX_FILE="$BUILD_DIR/${TARGET}.ihx"
BIN_FILE="$BUILD_DIR/${TARGET}.bin"

CHFLASHER_PY="$PROJECT_ROOT/chflasher.py"
CHFLASHER_URL="https://raw.githubusercontent.com/atc1441/chflasher/master/chflasher.py"

CONVERTER_PY="$PROJECT_ROOT/convert_ch559_keil_to_sdcc.py"

log() { printf '[INFO] %s\n' "$*"; }
err() { printf '[ERROR] %s\n' "$*" >&2; }

# -------------------------------
# Dependency checks
# -------------------------------
check_sdcc() {
    if ! command -v sdcc >/dev/null 2>&1; then
        err "sdcc not found"
        exit 1
    fi
}

check_python3() {
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3 not found"
        exit 1
    fi
}

have_objcopy() {
    command -v objcopy >/dev/null 2>&1 && return 0
    command -v gobjcopy >/dev/null 2>&1 && return 0
    return 1
}

# -------------------------------
# Setup
# -------------------------------
setup_pyusb() {
    check_python3
    log "Installing pyusb..."
    python3 -m pip install --upgrade pyusb
}

fetch_chflasher() {
    if [ -f "$CHFLASHER_PY" ]; then
        log "chflasher.py already exists"
        return
    fi

    log "Downloading chflasher.py from github.com/atc1441/chflasher"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$CHFLASHER_URL" -o "$CHFLASHER_PY"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$CHFLASHER_URL" -O "$CHFLASHER_PY"
    else
        err "curl or wget required to download chflasher.py"
        exit 1
    fi

    chmod +x "$CHFLASHER_PY"
}

setup() {
    log "Setup..."
    check_sdcc
    check_python3
    setup_pyusb
    fetch_chflasher
    log "Setup complete."
}

# -------------------------------
# Clean
# -------------------------------
clean() {
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    log "Clean done."
}

# -------------------------------
# Build
# -------------------------------
convert() {
    if [ ! -f "$CONVERTER_PY" ]; then
        err "Missing $CONVERTER_PY"
        exit 1
    fi

    if [ ! -f "$SRC_DIR/CH559.H" ]; then
        err "Missing src/CH559.H (place WCH original here)"
        exit 1
    fi

    log "Running header converter..."
    cd "$SRC_DIR"
    python3 "$CONVERTER_PY"
    cd "$PROJECT_ROOT"
}

build() {
    check_sdcc
    mkdir -p "$BUILD_DIR"

    if [ ! -f "$SRC_DIR/main.c" ]; then
        err "Missing src/main.c"
        exit 1
    fi

    convert

    log "Compiling main.c"
    sdcc --model-small -I"$SRC_DIR" --std-c99 --xram-size 0x1800 --xram-loc 0x0000 --code-size 0xF000 -c "$SRC_DIR/main.c" -o "$BUILD_DIR/main.rel"

    log "Linking"
    sdcc --model-small --xram-size 0x1800 --xram-loc 0x0000 --code-size 0xF000 -o "$HEX_FILE" "$BUILD_DIR/main.rel"

    if [ ! -f "$HEX_FILE" ]; then
        err "IHX not built"
        exit 1
    fi

    convert_hex_to_bin
}

# -------------------------------
# Convert IHX → BIN
# -------------------------------
convert_hex_to_bin() {
    log "Converting IHX -> BIN"

    if have_objcopy; then
        objcopy -I ihex -O binary "$HEX_FILE" "$BIN_FILE" 2>/dev/null \
        || gobjcopy -I ihex -O binary "$HEX_FILE" "$BIN_FILE"
    else
        python3 <<'EOF'
import sys
hex_path = sys.argv[1]
bin_path = sys.argv[2]

data = {}
max_addr = 0
with open(hex_path) as f:
    upper = 0
    for line in f:
        if not line.startswith(':'):
            continue
        length = int(line[1:3], 16)
        addr = int(line[3:7], 16)
        rectype = int(line[7:9], 16)
        payload = line[9:9+2*length]
        if rectype == 0:
            full = (upper << 16) + addr
            for i in range(length):
                b = int(payload[2*i:2*i+2], 16)
                data[full+i] = b
                max_addr = max(max_addr, full+i)
        elif rectype == 4:
            upper = int(payload, 16)

buf = bytearray(max(max_addr+1, 256))
for k, v in data.items():
    buf[k] = v
with open(bin_path, "wb") as f:
    f.write(buf)
EOF
        python3 -c "
import sys
hex_path = '$HEX_FILE'
bin_path = '$BIN_FILE'

data = {}
max_addr = 0
with open(hex_path) as f:
    upper = 0
    for line in f:
        if not line.startswith(':'):
            continue
        length = int(line[1:3], 16)
        addr = int(line[3:7], 16)
        rectype = int(line[7:9], 16)
        payload = line[9:9+2*length]
        if rectype == 0:
            full = (upper << 16) + addr
            for i in range(length):
                b = int(payload[2*i:2*i+2], 16)
                data[full+i] = b
                max_addr = max(max_addr, full+i)
        elif rectype == 4:
            upper = int(payload, 16)

buf = bytearray(max(max_addr+1, 256))
for k, v in data.items():
    buf[k] = v
with open(bin_path, 'wb') as f:
    f.write(buf)
"
    fi

    if [ -f "$BIN_FILE" ]; then
        size=$(stat -c%s "$BIN_FILE" 2>/dev/null || stat -f%z "$BIN_FILE" 2>/dev/null || echo 0)
        if [ "$size" -lt 256 ]; then
            python3 -c "
bin_path = '$BIN_FILE'
with open(bin_path, 'r+b') as f:
    f.seek(0, 2)
    current_size = f.tell()
    if current_size < 256:
        f.write(b'\x00' * (256 - current_size))
"
        fi
    fi
}

# -------------------------------
# Flash
# -------------------------------
flash() {
    if [ ! -f "$BIN_FILE" ]; then
        err "Binary missing, run build first"
        exit 1
    fi

    log "Put CH559 into bootloader and press enter"
    read -r _

    python3 "$CHFLASHER_PY" "$BIN_FILE"
    log "Flash finished."
}

# -------------------------------
# Dispatch
# -------------------------------
case "${1:-all}" in
    setup) setup ;;
    clean) clean ;;
    build) build ;;
    flash) flash ;;
    all)
        setup
        clean
        build
        flash
        ;;
    *)
        echo "Usage: $0 [setup|clean|build|flash|all]"
        exit 1
        ;;
esac
