#!/usr/bin/env python3
"""
KEIL TO SDCC HEADER CONVERTER

This script converts CH559.H microcontroller header files from Keil compiler 
syntax to SDCC (Small Device C Compiler) compatible syntax.

WHAT IT DOES:
- Converts Keil-style register definitions to SDCC format
- Handles Special Function Registers (SFR), bit declarations, and external memory declarations
- Preserves all original comments and formatting
- Protects the original file by creating a backup

WHY YOU NEED IT:
Keil and SDCC use different syntax for microcontroller register declarations. This 
script automatically translates them so you can use the same header file with SDCC.

KEY CONVERSIONS:
- sfr16 NAME = 0xNN;      →  __sfr16 __at (0xHHLL) NAME;
- sfr NAME = 0xNN;        →  __sfr __at (0xNN) NAME;
- sbit NAME = REG^b;      →  __sbit __at (0xXX) NAME;
- EXTERN TYPE NAME _AT_;  →  extern TYPE __at (...) NAME;
- memory qualifiers (xdata, idata, etc) are mapped to SDCC equivalents

USAGE:
    python3 convert.py

HOW IT WORKS:

  First run (if CH559.H.ORIGINAL does not exist):
    1. Checks if CH559.H exists and is not already converted
    2. Renames CH559.H → CH559.H.ORIGINAL (backup)
    3. Converts CH559.H.ORIGINAL and saves result to CH559.H
    4. Adds a marker comment to converted file so it won't be converted again

  Subsequent runs:
    1. Always reads from CH559.H.ORIGINAL (never modifies it)
    2. Regenerates CH559.H from CH559.H.ORIGINAL
    3. This lets you re-run the script if the original changes

SAFETY:
- The original Keil header is always preserved as CH559.H.ORIGINAL
- You can safely delete CH559.H and re-run the script to regenerate it
- The marker comment prevents "converting the converted"
"""

import re
import sys
from pathlib import Path

# This marker is added to converted files so the script can identify them
CONVERTED_MARKER = "// SDCC-CONVERTED CH559.H (auto-generated)"


def load_lines(path: Path):
    """
    Load a text file and return its contents as a list of lines.
    
    Args:
        path: Path to the file to load
        
    Returns:
        List of strings, one per line (without trailing newlines)
        
    Why latin-1?:
        The CH559.H header may contain non-ASCII characters in comments.
        latin-1 encoding handles any byte value (0-255), so it won't fail.
    """
    return path.read_text(encoding="latin-1").splitlines()


def build_sfr_addr_map(lines):
    """
    FIRST PASS: Build a lookup table of all Special Function Registers (SFR).
    
    Why we need this:
        Keil uses 'sbit NAME = REG^b;' syntax where 'b' is a bit number (0-7).
        SDCC needs the actual bit address (a number 0-255).
        
        Example: if P0 (an SFR) is at address 0x80, and we define 'sbit P0_0 = P0^0',
        the bit address is 0x80 + 0 = 0x80.
    
    Args:
        lines: List of lines from the original Keil header
        
    Returns:
        Dictionary mapping register names to their memory addresses.
        Example: {'P0': 0x80, 'P1': 0x90, 'P2': 0xA0, ...}
    """
    sfr_addr = {}
    # Pattern matches lines like: "sfr P0 = 0x80;"
    sfr_re = re.compile(r'^\s*sfr\s+(\w+)\s*=\s*0x([0-9A-Fa-f]+);')
    
    for line in lines:
        m = sfr_re.match(line)
        if m:
            name, addr_hex = m.groups()
            # Convert hex string (e.g., "80") to integer (e.g., 128)
            sfr_addr[name] = int(addr_hex, 16)
    
    return sfr_addr


def resolve_original_header(ch559_path: Path) -> Path:
    """
    Ensure we have CH559.H.ORIGINAL and return its path.
    
    This function handles the backup logic:
    
    CASE 1: CH559.H.ORIGINAL already exists
        → Return it (we're on a subsequent run)
        
    CASE 2: CH559.H.ORIGINAL doesn't exist, but CH559.H does
        → Check if CH559.H is already converted (has marker comment)
        → If yes: ERROR (we can't process it; user must restore backup)
        → If no: Rename CH559.H → CH559.H.ORIGINAL and return the new path
        
    CASE 3: Neither file exists
        → ERROR (nothing to convert)
    
    Args:
        ch559_path: Path to CH559.H in current directory
        
    Returns:
        Path to CH559.H.ORIGINAL (the original Keil header)
        
    Raises:
        sys.exit(1): If files are missing or in an invalid state
    """
    # The backup file is created by appending ".ORIGINAL" to the filename
    original = ch559_path.with_suffix(ch559_path.suffix + ".ORIGINAL")

    # Case 1: Backup already exists, use it
    if original.exists():
        return original

    # Case 3: Neither file exists
    if not ch559_path.exists():
        print("ERROR: CH559.H not found and CH559.H.ORIGINAL does not exist.", file=sys.stderr)
        sys.exit(1)

    # Check if the current CH559.H is already converted (has the marker)
    text = ch559_path.read_text(encoding="latin-1")
    if CONVERTED_MARKER in text:
        # Case 2b: It's already converted but backup is missing - this is dangerous
        print("ERROR: CH559.H appears to be a converted header, but CH559.H.ORIGINAL", file=sys.stderr)
        print("       is missing. Refusing to treat the converted file as original.", file=sys.stderr)
        print("       Restore your original as CH559.H.ORIGINAL and rerun.", file=sys.stderr)
        sys.exit(1)

    # Case 2a: Create the backup by renaming the original
    print(f"[INFO] First run detected, renaming {ch559_path.name} -> {original.name}")
    ch559_path.rename(original)
    return original


def convert_lines(lines):
    """
    Main conversion logic: Transform Keil syntax to SDCC syntax.
    
    This function processes each line and:
    1. Inserts SDCC compatibility macros (right after the first #ifndef)
    2. Converts Keil-style 'bit' to SDCC-style '__bit'
    3. Strips memory qualifiers from typedef lines (xdata, idata, etc.)
    4. Converts sfr16 declarations
    5. Converts sfr declarations
    6. Converts sbit declarations
    7. Converts EXTERN declarations
    
    Args:
        lines: List of lines from the original Keil header
        
    Returns:
        List of converted lines
    """
    
    # Build a map of all SFR addresses for converting 'sbit' declarations later
    sfr_addr = build_sfr_addr_map(lines)
    out = []
    sdcc_macros_inserted = False

    # Patterns (regular expressions) for detecting Keil constructs
    sfr16_re = re.compile(r'^(\s*)sfr16\s+(\w+)\s*=\s*0x([0-9A-Fa-f]+);(.*)$')
    sfr_re   = re.compile(r'^(\s*)sfr\s+(\w+)\s*=\s*0x([0-9A-Fa-f]+);(.*)$')
    sbit_re  = re.compile(r'^(\s*)sbit\s+(\w+)\s*=\s*(\w+)\s*\^\s*([0-7]);(.*)$')
    xreg_re  = re.compile(r'^(\s*)EXTERN\s+(.+?)\s+(\w+)\s+_AT_\s+0x([0-9A-Fa-f]+);(.*)$')

    for line in lines:
        # STEP 1: Insert compatibility macros
        # We insert these right after the first #ifndef guard (usually __BASE_TYPE__)
        # This ensures the macros are defined before any declarations that use them
        if (not sdcc_macros_inserted) and line.startswith('#ifndef'):
            out.append(line)
            out.append('')
            out.append('#ifdef __SDCC__')
            # These macros map Keil memory space keywords to SDCC equivalents
            # Example: if code says "unsigned char xdata foo;", after macro expansion
            #          it becomes "unsigned char __xdata foo;" which SDCC understands
            out.append('#define data  __data')    # internal data memory
            out.append('#define idata __idata')   # internal data memory (indirect)
            out.append('#define xdata __xdata')   # external data memory
            out.append('#define pdata __pdata')   # paged external data memory
            out.append('#define code  __code')    # program memory (ROM)
            out.append('#endif')
            out.append('')
            sdcc_macros_inserted = True
            continue

        # STEP 2: Replace 'bit' with '__bit' in the whole line
        # Keil uses 'bit' as a keyword, SDCC uses '__bit'
        # We skip this for comments (lines starting with //)
        if 'bit' in line and not line.strip().startswith('//'):
            line = re.sub(r'\bbit\b', '__bit', line)

        # STEP 3: Strip memory qualifiers from typedef lines
        # Example: "typedef unsigned char xdata UINT8X;" → "typedef unsigned char UINT8X;"
        # Why? Because we've mapped 'xdata' to '__xdata' via macro, but SDCC
        # doesn't allow memory qualifiers in typedef definitions. We'll apply the
        # qualifiers when actually declaring variables of this type.
        stripped = line.lstrip()
        if stripped.startswith('typedef') and any(
                kw in stripped for kw in ('data', 'idata', 'xdata', 'pdata', 'code')
        ):
            indent_len = len(line) - len(stripped)
            indent = line[:indent_len]

            # Preserve any trailing comment (e.g., "// my typedef")
            code_part, *comment_part = stripped.split('//', 1)
            comment_suffix = ''
            if comment_part:
                comment_suffix = '//' + comment_part[0]

            # Remove all memory qualifiers from the code part
            for kw in ('data', 'idata', 'xdata', 'pdata', 'code'):
                code_part = re.sub(r'\b' + kw + r'\b', '', code_part)

            # Clean up extra whitespace (e.g., multiple spaces)
            code_part = re.sub(r'\s+', ' ', code_part).rstrip()

            # Rebuild: indent + cleaned typedef + original comment
            if comment_suffix and not comment_suffix.startswith(' '):
                comment_suffix = ' ' + comment_suffix
            line = indent + code_part + comment_suffix

        # STEP 4: Convert sfr16 (16-bit Special Function Register)
        # Keil:  sfr16 DPTR = 0x82;
        # SDCC:  __sfr16 __at (0x8382) DPTR;
        # Note: 0x8382 = (0x83 << 8) | 0x82 (little-endian pairing)
        m = sfr16_re.match(line)
        if m:
            indent, name, addr_hex, comment = m.groups()
            addr = int(addr_hex, 16)
            # For a 16-bit SFR at address N, the high byte is at N+1 and low byte is at N
            word_addr = ((addr + 1) << 8) | addr
            out.append(f'{indent}__sfr16 __at (0x{word_addr:04X}) {name};{comment}')
            continue

        # STEP 5: Convert sfr (8-bit Special Function Register)
        # Keil:  sfr P0 = 0x80;
        # SDCC:  __sfr __at (0x80) P0;
        m = sfr_re.match(line)
        if m:
            indent, name, addr_hex, comment = m.groups()
            addr_hex = addr_hex.upper()  # Normalize to uppercase hex
            out.append(f'{indent}__sfr __at (0x{addr_hex}) {name};{comment}')
            continue

        # STEP 6: Convert sbit (bit within a Special Function Register)
        # Keil:  sbit EA = IE^7;     (EA is bit 7 of IE register)
        # SDCC:  __sbit __at (0xAF) EA;  (0xAF is the calculated bit address)
        # Formula: bit_address = sfr_address + bit_number
        m = sbit_re.match(line)
        if m:
            indent, name, base, bit_str, comment = m.groups()
            # Look up the SFR address (e.g., IE = 0xA8)
            base_addr = sfr_addr.get(base)
            if base_addr is None:
                # If we don't know the base register address, leave the line unchanged
                # (This shouldn't happen with a well-formed header)
                out.append(line)
            else:
                # Calculate the bit address: base address + bit position (0-7)
                bit_addr = base_addr + int(bit_str)
                out.append(f'{indent}__sbit __at (0x{bit_addr:02X}) {name};{comment}')
            continue

        # STEP 7: Convert EXTERN (external memory variable declaration)
        # Keil:  EXTERN unsigned char xdata DATA_ARRAY _AT_ 0x2000;
        # SDCC:  extern unsigned char __at (0x2000) DATA_ARRAY;
        m = xreg_re.match(line)
        if m:
            indent, typestr, name, addr_hex, comment = m.groups()
            addr_hex = addr_hex.upper()  # Normalize to uppercase hex
            out.append(f'{indent}extern {typestr} __at (0x{addr_hex}) {name};{comment}')
            continue

        # Fallback: If the line doesn't match any conversion pattern, keep it unchanged
        out.append(line)

    return out


def main():
    """
    Main entry point: orchestrate the conversion process.
    
    1. Locate or create CH559.H.ORIGINAL
    2. Load the original header file
    3. Convert all lines
    4. Write converted header back to CH559.H
    5. Add marker comment so we don't convert it again
    """
    # Always operate on CH559.H in the current working directory
    ch559_path = Path("CH559.H")

    # Print summary before making any changes
    print("\n" + "="*70)
    print("KEIL → SDCC HEADER CONVERTER")
    print("="*70)
    print("\nThis script converts Keil-style CH559.H to SDCC-compatible format.")
    print("\nKEY CONVERSIONS:")
    print("  • sfr16 declarations  →  __sfr16 __at (...)")
    print("  • sfr declarations    →  __sfr __at (...)")
    print("  • sbit declarations   →  __sbit __at (...)")
    print("  • Memory qualifiers   →  SDCC macros (xdata → __xdata, etc.)")
    print("\nFILE HANDLING:")
    print("  • Original backup:    CH559.H.ORIGINAL (never modified)")
    print("  • Converted output:   CH559.H (regenerated each run)")
    print("  • Safe to delete:     CH559.H (just re-run script to regenerate)")
    print("\n" + "="*70 + "\n")

    # Get the path to the original header (create backup if needed)
    original_path = resolve_original_header(ch559_path)
    
    # Load the original file as lines
    original_lines = load_lines(original_path)

    # Perform the conversion
    converted_body = convert_lines(original_lines)

    # Add header banner to the converted file
    # This marker prevents the script from accidentally "converting the converted"
    banner = [
        CONVERTED_MARKER,
        "// DO NOT EDIT THIS FILE DIRECTLY.",
        "// Edit CH559.H.ORIGINAL and re-run convert.py instead.",
        ""
    ]
    
    # Join all lines and ensure file ends with newline
    out_text = "\n".join(banner + converted_body) + "\n"

    # Write the converted header to CH559.H
    ch559_path.write_text(out_text, encoding="latin-1")
    print(f"[INFO] Converted {original_path.name} -> {ch559_path.name}")


if __name__ == "__main__":
    main()
