# CH559 Keil → SDCC Header Conversion Tool

### *What this repository is, why it exists, and how to use it*

This project provides a **fully automated converter** that takes the **official WCH CH559 microcontroller header file** (written for the *Keil C51* compiler) and generates a new version of that header that is **100% compatible with the SDCC compiler**.

Here is a link to the official SDK for CH559, which includes the file that this operates on:

https://www.wch.cn/downloads/CH559EVT_ZIP.html

---

## 🌟 What is the CH559?

The **CH559** is an 8051-based microcontroller made by WCH. It's inexpensive and popular because it includes:

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
* hope they didn't introduce errors

This was tedious, error-prone, and discouraging.

---

## ✅ The Solution — This Repository

This project provides:

### **1. An automatic converter script**

`convert_ch559_keil_to_sdcc.py`

You feed it WCH's original `CH559.H`, and it outputs a fully SDCC-compatible version. The script:

* Finds all SFRs and computes bit addresses
* Converts 16-bit SFRs into SDCC's `__sfr16` format
* Rewrites `sbit` assignments
* Rewrites Keil's `_AT_` syntax into SDCC's `__at()`
* Inserts a compatibility shim so Keil memory keywords (`data`, `idata`, `xdata`, `code`) map cleanly to SDCC equivalents

It preserves every comment, macro, typedef, and constant — only the parts that SDCC cannot compile are rewritten.

### **2. A clean SDCC test program**

`main.c`

A simple LED-blink program that verifies the generated header actually works when compiled with SDCC.

### **3. A documented, repeatable workflow**

Anyone can now:

```bash
python3 convert.py
sdcc -mmcs51 main.c
```

— and have a working CH559 project using SDCC.

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

1. Place `CH559.H` (from WCH) in the same directory as `convert.py`.

2. Run the converter:

   ```bash
   python3 convert_ch559_keil_to_sdcc.py
   ```

   This will:
   - Create `CH559.H.ORIGINAL` (backup of your original Keil header)
   - Generate a converted `CH559.H` with SDCC syntax
   - Print a summary of what it did

3. Build the test program:

   ```bash
   sdcc -mmcs51 main.c
   ```

4. Flash the generated hex file to your CH559 board.

If it compiles and runs, your toolchain is working correctly.

---

## 🔄 How the converter works

### File handling

- **First run**: If `CH559.H.ORIGINAL` doesn't exist, the script renames your original `CH559.H` to `CH559.H.ORIGINAL` and generates a converted version.
- **Subsequent runs**: The script always reads from `CH559.H.ORIGINAL` and regenerates `CH559.H`.
- **Safety**: Your original Keil header is never modified. You can safely delete `CH559.H` and re-run the script anytime.

### What gets converted

| Keil Syntax | SDCC Equivalent |
|---|---|
| `sfr P1 = 0x90;` | `__sfr __at (0x90) P1;` |
| `sbit P1_0 = P1^0;` | `__sbit __at (0x90) P1_0;` |
| `sfr16 ROM_ADDR = 0x84;` | `__sfr16 __at (0x8584) ROM_ADDR;` |
| `EXTERN UINT8XV LED_DATA _AT_ 0x2882;` | `extern UINT8XV __at (0x2882) LED_DATA;` |
| `unsigned char xdata foo;` | `unsigned char __xdata foo;` (via macro) |

---

## 📌 Who is this for?

* Makers / hobbyists using the CH559
* Developers wanting a free/open compiler
* Anyone frustrated with Keil's limitations
* Students learning embedded C
* Engineers integrating the CH559 into open hardware

If you're using SDCC and you need CH559 register definitions, this repository gives you everything required.

---

## 🔧 Flashing your CH559

### Using chflasher.py

Once you have a compiled binary (`.bin` file), you can flash it directly to your CH559 via USB using **chflasher.py** — an open-source Python flashing tool created by [Aaron Christophel (ATCnetz.de)](https://github.com/atc1441/chflasher).

**What it does:**
- Detects your CH559 device over USB
- Erases the existing firmware
- Writes your new binary to flash
- Verifies the write was successful
- Supports CH551, CH552, CH554, CH558, and CH559

**How to use it:**

```bash
python3 chflasher.py main.bin
```

The device will enter bootloader mode automatically (via USB reset). Place your CH559 in bootloader mode and the flashing will begin.

**Setup (one-time):**

Install pyusb:

```bash
pip install pyusb
```

On Linux, you may need to configure udev rules for USB access (the script will guide you if needed).

On Windows, you may need [Zadig](https://zadig.akeo.ie/) to install the correct libusb driver.

---

## 🏗️ Build and Flash Automation

### Optional: build_and_flash.sh

If you want a single command to build and flash, we provide an optional bash script that:

- Checks for required tools (SDCC, Python 3)
- Runs the converter
- Compiles your code with SDCC
- Converts the output to binary format
- Flashes the result to your CH559

**Usage:**

```bash
./build_and_flash.sh all      # setup + clean + build + flash
./build_and_flash.sh setup    # install dependencies
./build_and_flash.sh build    # compile only
./build_and_flash.sh flash    # flash only
./build_and_flash.sh clean    # clean build artifacts
```

This script expects a project structure like:

```
project/
├── src/
│   ├── main.c
│   ├── DEBUG.C
│   └── CH559.H
├── chflasher.py (auto-downloaded if missing)
├── convert_ch559_keil_to_sdcc.py
└── build_and_flash.sh
```

---

## 🛠️ Hardware Setup

### Recommended: ElectroDragon CH559 Dev Board

For beginners, we recommend the **[ElectroDragon CH559 Development Board](https://www.electrodragon.com/product/ch559-usb-mcu-board/)**, which includes:

- CH559 microcontroller pre-populated
- USB Type-B connector for flashing and power
- Built-in LEDs and buttons for testing
- Ready to program

This board is perfect for prototyping and has good community support.

---

## 📦 Manual Build Setup

### Direct command-line compile

Assuming `CH559.H` and `main.c` are in the current directory:

```bash
sdcc -mmcs51 main.c
```

This will produce `main.ihx` plus intermediate files.

To convert to hex format:

```bash
packihx main.ihx > main.hex
```

### Optional Makefile

If you prefer automated builds:

```make
SDCC      = sdcc
SDCCFLAGS = -mmcs51

all: main.hex

main.rel: main.c CH559.H
	$(SDCC) $(SDCCFLAGS) -c main.c

main.ihx: main.rel
	$(SDCC) $(SDCCFLAGS) main.rel

main.hex: main.ihx
	packihx main.ihx > main.hex

clean:
	rm -f *.rel *.lst *.asm *.map *.sym *.ihx *.hex
```

Then:

```bash
make
```

will compile and generate `main.hex` ready for flashing.

---

## 📋 What's included

- **convert_ch559_keil_to_sdcc.py** — The converter script (with detailed inline documentation)
- **main.c** — Minimal test program demonstrating SFR and sbit usage
- **build_and_flash.sh** — Optional automation script for compile and flash
- **chflasher.py** — USB flasher tool (auto-downloaded if missing)
- **README.md** — This file

---

## 🙏 Attribution

**chflasher.py** is maintained by [Aaron Christophel (ATCnetz.de)](https://github.com/atc1441/chflasher) and is used under the terms of its open-source license. This tool is essential for flashing CH55x series microcontrollers over USB and is credited in all documentation and usage.

---
