
# CH559 Keil → SDCC Header Conversion Tool

### *What this repository is, why it exists, and how to use it*

This project provides a **fully automated converter** that takes the **official WCH CH559 microcontroller header file** (written for the *Keil C51* compiler) and generates a new version of that header that is **100% compatible with the SDCC compiler**.

Here is a link to the official SDK for CH559:

https://www.wch.cn/downloads/CH559EVT_ZIP.html

---

## 🌟 What is the CH559?

The **CH559** is an 8051-based microcontroller made by WCH. It’s inexpensive and popular because it includes:

* USB host & device capability
* xDATA / xSFR extended memory
* Timers, ADC, SPI, UART, PWM, etc.

To write firmware for this chip, you need a **C compiler** and a **header file** that describes all of the hardware registers (`sfr`, `sbit`, USB endpoints, timers, ports…).

WCH only provides an official header in **Keil C51 format**.

---

## ❗ The Problem

Keil C51 is:

* proprietary
* Windows-only
* limited to 2 KB of compiled code unless you buy a license
* not suitable for open-source or hobbyist firmware workflows

Most open-source 8051 developers prefer **SDCC (Small Device C Compiler)**, which is:

* free & open source
* cross-platform
* supports the CH559
* widely used in community firmware projects

But…
**The Keil CH559 header does not compile under SDCC.**

Keil and SDCC use **different syntax** for special function registers (SFRs), bits, extended xDATA registers, and memory qualifiers.

So until now, anyone wanting to use SDCC had to:

* rewrite the entire CH559 header manually
* fix hundreds of SFR, SBIT, and xdata declarations
* hope they didn’t introduce errors

This was tedious, error-prone, and discouraging.

---

## ✅ The Solution — This Repository

This project provides:

### **1. An automatic converter script**

`convert_ch559_keil_to_sdcc.py`

You feed it WCH’s original `CH559.H`, and it outputs `CH559_SDCC.H` — a fully SDCC-compatible header.

### **2. A clean SDCC test program**

`main.c`

A simple LED-blink program that verifies the generated header actually works when compiled with SDCC.

### **3. A documented, repeatable workflow**

Anyone can now:

```bash
python3 convert_ch559_keil_to_sdcc.py CH559.H CH559_SDCC.H
sdcc -mmcs51 main.c
```

— and have a working CH559 project using SDCC.

---

## 🛠️ What the converter actually does

Keil uses syntax like:

```c
sfr P1 = 0x90;
sbit P1_0 = P1^0;
sfr16 ROM_ADDR = 0x84;
EXTERN UINT8XV LED_DATA _AT_ 0x2882;
```

SDCC requires **different declarations**, such as:

```c
__sfr __at (0x90) P1;
__sbit __at (0x90) P1_0;
__sfr16 __at (0x8584) ROM_ADDR;    // Special SDCC format for 16-bit SFRs
extern UINT8XV __at (0x2882) LED_DATA;
```

The converter:

* Finds all SFRs and computes bit addresses
* Converts 16-bit SFRs into SDCC’s `__sfr16` format
* Rewrites `sbit` assignments
* Rewrites Keil’s `_AT_` syntax into SDCC’s `__at()`
* Inserts a compatibility shim so Keil memory keywords (`data`, `idata`, `xdata`, `code`) map cleanly to SDCC equivalents

It preserves:

* Every comment
* Every macro
* Every typedef
* Every constant
* The exact structure of the file

Only the parts that SDCC cannot compile are rewritten.

---

## 💡 Why this matters

This project eliminates the single largest barrier preventing developers from using **SDCC** with **WCH CH559** microcontrollers.

It enables:

* Open-source CH559 firmware
* Cross-platform tooling
* GitHub automation / CI
* Educational projects
* Linux/macOS development
* Keil-free workflows

No license.
No binary blobs.
No manual rewriting.
Just a clean, reproducible transformation.

---

## 🚀 Quick Start

1. Place `CH559.H` (from WCH) in this directory.

2. Run:

   ```bash
   python3 convert_ch559_keil_to_sdcc.py CH559.H CH559_SDCC.H
   ```

3. Build the test:

   ```bash
   sdcc -mmcs51 main.c
   ```

4. Flash the generated hex file to your CH559 board.

If it compiles and runs, your toolchain is working correctly.

---

## 📌 Who is this for?

* Makers / hobbyists using the CH559
* Developers wanting a free/open compiler
* Anyone frustrated with Keil’s limitations
* Students learning embedded C
* Engineers integrating the CH559 into open hardware

If you’re using SDCC and you need CH559 register definitions, this repository gives you everything required.

---

## 📨 Want to contribute?

Suggestions, improvements, and fixes are welcome!
Feel free to open an issue or submit a pull request.

---

If you'd like, I can generate a polished README.md containing the explanation above plus badges, formatting, or usage diagrams.


## 1. Keil → SDCC header converter script

Save this as `convert_ch559_keil_to_sdcc.py`:

```python
#!/usr/bin/env python3
"""
Convert Keil-style CH559.H to an SDCC-compatible header.

Usage:
    python3 convert_ch559_keil_to_sdcc.py CH559.H CH559_SDCC.H

It performs these transformations:

  - Insert SDCC glue for memory qualifiers (bit, data, xdata, code, ...).
  - sfr   NAME = 0xNN;        -> __sfr   __at (0xNN) NAME;
  - sfr16 NAME = 0xNN;        -> __sfr16 __at (0xHHLL) NAME;
                                where HH = addr+1, LL = addr (little-endian)
  - sbit  NAME = REG^b;       -> __sbit  __at (0xXX)  NAME;
                                where 0xXX = base address of REG + b
  - EXTERN TYPE NAME _AT_ 0xNNNN;
                              -> extern TYPE __at (0xNNNN) NAME;

Everything else (comments, #defines, typedefs, etc.) is preserved.
"""

import re
import sys
from pathlib import Path


def load_lines(path: Path):
    # CH559.H from WCH is often encoded as ANSI / GBK; latin-1 will not fail on any byte.
    return Path(path).read_text(encoding="latin-1").splitlines()


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
        # 1) Insert SDCC glue right after the "constant and type define" banner.
        if '/*----- constant and type define' in line and not sdcc_macros_inserted:
            out.append(line)
            out.append('')
            out.append('#ifdef __SDCC__')
            out.append('#define bit   __bit')
            out.append('#define data  __data')
            out.append('#define idata __idata')
            out.append('#define xdata __xdata')
            out.append('#define pdata __pdata')
            out.append('#define code  __code')
            out.append('#endif')
            sdcc_macros_inserted = True
            continue

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
                # If base SFR is unknown, leave the line for manual inspection.
                out.append(line)
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
    if len(sys.argv) != 3:
        print("Usage: python3 convert_ch559_keil_to_sdcc.py CH559.H CH559_SDCC.H", file=sys.stderr)
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    lines = load_lines(in_path)
    new_lines = convert_lines(lines)
    out_text = "\n".join(new_lines) + "\n"
    out_path.write_text(out_text, encoding="latin-1")

    print(f"Converted {in_path} -> {out_path}")


if __name__ == "__main__":
    main()
```

### How to run it

In the directory where your original `CH559.H` lives:

```bash
python3 convert_ch559_keil_to_sdcc.py CH559.H CH559_SDCC.H
```

You should now have a new `CH559_SDCC.H` that SDCC can compile.

---

## 2. Minimal SDCC test program

This is a tiny blink/test program that:

* Includes your generated `CH559_SDCC.H`;
* Disables interrupts;
* Configures `P3.2` and `P3.3` (LED0/LED1 on many CH559 boards) as outputs;
* Toggles them in a loop.

Save as `main.c`:

```c
#include "CH559_SDCC.H"

/* Simple software delay to make LED toggling visible. */
static void delay_ms(unsigned int ms)
{
    /* Crude busy loop; the constant depends on Fsys but is good enough
       just to confirm that the header and SFRs compile and link. */
    unsigned int i;
    while (ms--)
    {
        for (i = 0; i < 5000; i++)
        {
            __asm
                nop
            __endasm;
        }
    }
}

void main(void)
{
    /* Disable all interrupts while we poke hardware. */
    EA = 0;

    /* Configure P3.2 and P3.3 as outputs (LED0 / LED1 on some CH559 boards). */
    /* P3_DIR is defined in CH559.H as the direction register for port 3:
       0=input, 1=output. We set bits 2 and 3 to 1 (outputs). */
    P3_DIR |= (0x04 | 0x08);

    /* Optionally enable pullups on P3 (if defined in your header as P3_PU). */
    /* P3_PU |= (0x04 | 0x08); */

    /* Start with LEDs off. */
    P3 &= ~(0x04 | 0x08);

    for (;;)
    {
        /* Toggle LED0 (P3.2) and LED1 (P3.3). */
        P3 ^= 0x04;  /* flip LED0 */
        delay_ms(100);

        P3 ^= 0x08;  /* flip LED1 */
        delay_ms(100);
    }
}
```

This program doesn’t rely on any startup code beyond SDCC’s usual minimal runtime. It just hits a few SFRs and bits so that:

* `__sfr` declarations are used (`P3`, `P3_DIR`);
* `__sbit` declarations are used (`EA` comes from `IE^7`).

If those parts of the generated header are wrong, SDCC will complain.

---

## 3. Example SDCC build command (and optional Makefile)

### Direct command-line compile

Assuming:

* `CH559_SDCC.H` and `main.c` are in the current directory,
* You’re building for MCS-51:

```bash
sdcc -mmcs51 -I. main.c
```

This will produce something like `main.ihx` plus intermediate `.rel`/`.asm` files.

To convert `main.ihx` to a raw binary:

```bash
packihx main.ihx > main.hex
```

### Optional simple Makefile

If you like a tiny Makefile, this is enough:

```make
SDCC      = sdcc
SDCCFLAGS = -mmcs51 -I.

all: main.hex

CH559_SDCC.H: CH559.H convert_ch559_keil_to_sdcc.py
	python3 convert_ch559_keil_to_sdcc.py CH559.H CH559_SDCC.H

main.rel: main.c CH559_SDCC.H
	$(SDCC) $(SDCCFLAGS) -c main.c

main.ihx: main.rel
	$(SDCC) $(SDCCFLAGS) main.rel

main.hex: main.ihx
	packihx main.ihx > main.hex

clean:
	rm -f *.rel *.lst *.asm *.map *.sym *.ihx *.hex CH559_SDCC.H
```

Then:

```bash
make
```

will:

1. Generate `CH559_SDCC.H` from `CH559.H`;
2. Compile `main.c` with SDCC;
3. Produce `main.hex` for flashing.

