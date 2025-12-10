#!/usr/bin/env python3
"""
In-place conversion of Keil-style CH559.H to an SDCC-compatible header.

Usage:
    python3 convert.py

Behaviour:

  - Operates on CH559.H in the current directory.

  - On first run:
      * If CH559.H.ORIGINAL does not exist and CH559.H is not yet converted,
        CH559.H is renamed to CH559.H.ORIGINAL.
      * CH559.H.ORIGINAL is converted and written back to CH559.H.

  - On subsequent runs:
      * CH559.H.ORIGINAL is always used as the source.
      * CH559.H is regenerated from CH559.H.ORIGINAL.
      * CH559.H.ORIGINAL is never overwritten.

  - The converted CH559.H starts with a marker comment so the script can
    recognise converted files and avoid "converting the converted".
"""

import re
import sys
from pathlib import Path

CONVERTED_MARKER = "// SDCC-CONVERTED CH559.H (auto-generated)"


def load_lines(path: Path):
    return path.read_text(encoding="latin-1").splitlines()


def build_sfr_addr_map(lines):
    """
    First pass: collect all 'sfr NAME = 0xNN;' so we can compute
    bit addresses for 'sbit NAME = REG^b;'.
    """
    sfr_addr = {}
    sfr_re = re.compile(r'^\s*sfr\s+(\w+)\s*=\s*0x([0-9A-Fa-f]+);')
    for line in lines:
        m = sfr_re.match(line)
        if m:
            name, addr_hex = m.groups()
            sfr_addr[name] = int(addr_hex, 16)
    return sfr_addr


def resolve_original_header(ch559_path: Path) -> Path:
    """
    Ensure we have CH559.H.ORIGINAL and return its path.

    - If CH559.H.ORIGINAL exists, use it as the source.
    - Otherwise:
        - If CH559.H does not exist, abort.
        - If CH559.H already contains the converted marker, abort (we refuse
          to treat a converted header as the original).
        - Else rename CH559.H -> CH559.H.ORIGINAL and use that.
    """
    original = ch559_path.with_suffix(ch559_path.suffix + ".ORIGINAL")

    if original.exists():
        return original

    if not ch559_path.exists():
        print("ERROR: CH559.H not found and CH559.H.ORIGINAL does not exist.", file=sys.stderr)
        sys.exit(1)

    text = ch559_path.read_text(encoding="latin-1")
    if CONVERTED_MARKER in text:
        print("ERROR: CH559.H appears to be a converted header, but CH559.H.ORIGINAL", file=sys.stderr)
        print("       is missing. Refusing to treat the converted file as original.", file=sys.stderr)
        print("       Restore your original as CH559.H.ORIGINAL and rerun.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] First run detected, renaming {ch559_path.name} -> {original.name}")
    ch559_path.rename(original)
    return original


def convert_lines(lines):
    sfr_addr = build_sfr_addr_map(lines)
    out = []
    sdcc_macros_inserted = False

    # Patterns for the constructs we want to rewrite.
    sfr16_re = re.compile(r'^(\s*)sfr16\s+(\w+)\s*=\s*0x([0-9A-Fa-f]+);(.*)$')
    sfr_re   = re.compile(r'^(\s*)sfr\s+(\w+)\s*=\s*0x([0-9A-Fa-f]+);(.*)$')
    sbit_re  = re.compile(r'^(\s*)sbit\s+(\w+)\s*=\s*(\w+)\s*\^\s*([0-7]);(.*)$')
    xreg_re  = re.compile(r'^(\s*)EXTERN\s+(.+?)\s+(\w+)\s+_AT_\s+0x([0-9A-Fa-f]+);(.*)$')

    for line in lines:
        # 1) Insert SDCC macros right after the first #ifndef guard,
        #    wherever it appears in the file (typically __BASE_TYPE__).
        if (not sdcc_macros_inserted) and line.startswith('#ifndef'):
            out.append(line)
            out.append('')
            out.append('#ifdef __SDCC__')
            # Map Keil memory qualifiers to SDCC memory spaces.
            # We strip these keywords from typedef lines below, so typedefs
            # become legal SDCC syntax.
            out.append('#define data  __data')
            out.append('#define idata __idata')
            out.append('#define xdata __xdata')
            out.append('#define pdata __pdata')
            out.append('#define code  __code')
            out.append('#endif')
            out.append('')
            sdcc_macros_inserted = True
            continue

        # Pre-process: replace 'bit' with '__bit' in typedefs and declarations
        if 'bit' in line and not line.strip().startswith('//'):
            line = re.sub(r'\bbit\b', '__bit', line)

        # Pre-process: in typedef lines, strip standalone 'data' / 'idata'
        # / 'xdata' / 'pdata' / 'code' so that, for example:
        #   typedef unsigned char  xdata            UINT8X;
        # becomes:
        #   typedef unsigned char UINT8X;
        stripped = line.lstrip()
        if stripped.startswith('typedef') and any(
                kw in stripped for kw in ('data', 'idata', 'xdata', 'pdata', 'code')
        ):
            indent_len = len(line) - len(stripped)
            indent = line[:indent_len]

            # Separate any trailing // comment so we don't mangle it.
            code_part, *comment_part = stripped.split('//', 1)
            comment_suffix = ''
            if comment_part:
                comment_suffix = '//' + comment_part[0]

            for kw in ('data', 'idata', 'xdata', 'pdata', 'code'):
                code_part = re.sub(r'\b' + kw + r'\b', '', code_part)

            # Normalise whitespace in the typedef
            code_part = re.sub(r'\s+', ' ', code_part).rstrip()

            # Rebuild the line with original indent and comment (if any)
            if comment_suffix and not comment_suffix.startswith(' '):
                comment_suffix = ' ' + comment_suffix
            line = indent + code_part + comment_suffix

        # 2) sfr16 NAME = 0xNN;  ->  __sfr16 __at (0xHHLL) NAME;
        #    where HH = addr+1, LL = addr (little-endian SFR pair).
        m = sfr16_re.match(line)
        if m:
            indent, name, addr_hex, comment = m.groups()
            addr = int(addr_hex, 16)
            word_addr = ((addr + 1) << 8) | addr
            out.append(f'{indent}__sfr16 __at (0x{word_addr:04X}) {name};{comment}')
            continue

        # 3) sfr NAME = 0xNN;    ->  __sfr __at (0xNN) NAME;
        m = sfr_re.match(line)
        if m:
            indent, name, addr_hex, comment = m.groups()
            addr_hex = addr_hex.upper()
            out.append(f'{indent}__sfr __at (0x{addr_hex}) {name};{comment}')
            continue

        # 4) sbit NAME = REG^b;  ->  __sbit __at (0xXX) NAME;  (bit address)
        m = sbit_re.match(line)
        if m:
            indent, name, base, bit_str, comment = m.groups()
            base_addr = sfr_addr.get(base)
            if base_addr is None:
                out.append(line)  # leave as-is if we don't know the base
            else:
                bit_addr = base_addr + int(bit_str)
                out.append(f'{indent}__sbit __at (0x{bit_addr:02X}) {name};{comment}')
            continue

        # 5) EXTERN TYPE NAME _AT_ 0xNNNN; -> extern TYPE __at (0xNNNN) NAME;
        m = xreg_re.match(line)
        if m:
            indent, typestr, name, addr_hex, comment = m.groups()
            addr_hex = addr_hex.upper()
            out.append(f'{indent}extern {typestr} __at (0x{addr_hex}) {name};{comment}')
            continue

        # Fallback: keep line unchanged.
        out.append(line)

    return out


def main():
    # Always operate on CH559.H in current directory.
    ch559_path = Path("CH559.H")

    original_path = resolve_original_header(ch559_path)
    original_lines = load_lines(original_path)

    converted_body = convert_lines(original_lines)

    # Prepend marker so we can recognise the converted header later
    banner = [
        CONVERTED_MARKER,
        "// DO NOT EDIT THIS FILE DIRECTLY.",
        "// Edit CH559.H.ORIGINAL and re-run convert.py instead.",
        ""
    ]
    out_text = "\n".join(banner + converted_body) + "\n"

    ch559_path.write_text(out_text, encoding="latin-1")
    print(f"[INFO] Converted {original_path.name} -> {ch559_path.name}")


if __name__ == "__main__":
    main()
