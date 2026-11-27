# FE Tools

Tools and reference material for examining, configuring, backing up, and programming **Frequency Electronics FE-5650A / FE-5680A rubidium frequency standards**.

The repository brings together a browser-based serial dashboard, Python utilities, a separate PSD813F1V hardware programmer, firmware archives, and hardware/firmware documentation.

## [Dashboard](Dashboard/) and [Reference](Reference/)

**[`fe-dashboard.html`](https://ioccy.github.io/fe-tools/Dashboard/fe-dashboard.html)** — a self-contained, offline dashboard that communicates over the browser's **Web Serial API** to read device information and measurements, adjust frequency and modify device settings.

**[`DDS60_4_1_Technical_Reference.html`](https://ioccy.github.io/fe-tools/Reference/DDS60_4_1_Technical_Reference.html)** — a self-contained, offline technical reference. Provides commands catalog, NVRAM map, configuration and math reference.

## [Firmware](Firmware/)

| Archive | Contents/purpose |
| --- | --- |
| [`fe5650a-fw-4.1.zip`](Firmware/fe5650a-fw-4.1.zip) | FE-5650A firmware archive, version **4.1**. |
| [`fe5680a-fw-3.2.zip`](Firmware/fe5680a-fw-3.2.zip) | FE-5680A firmware archive, version **3.2**. |

## Python [Scripts](Scripts/)

### [`fe-nvram.py`](Scripts/fe-nvram.py): Read, display, write, or edit NVRAM images.

**Command switches:**

| Switch | Meaning |
| --- | --- |
| `--read FILE` | Read device settings and reconstruct a 1 KiB NVRAM image. |
| `--show FILE` | Display decoded settings from an image. |
| `--write FILE` | Write supported settings from an image to the device. |
| `--set-sn SN` | Set the serial number in an existing image. |
| `--set-ot TICKS` | Set operating time in an existing image, in **20-minute ticks**. |
| `--port PORT` | Serial port; required for `--read` and `--write` only. |

Use one of `--read`, `--show`, or `--write`, **or** one or both `--set-sn` / `--set-ot` switches with a positional image filename. The `--set-*` switches cannot be combined with device operations or `--port`.

```sh
# Read device settings into a 1 KiB image
python Scripts/fe-nvram.py --read nvram.bin --port COM4

# Show a saved image
python Scripts/fe-nvram.py --show nvram.bin

# Write supported settings from a saved image
python Scripts/fe-nvram.py --write nvram.bin --port COM4

# Change the serial number in a file
python Scripts/fe-nvram.py --set-sn 76189 nvram.bin

# Reset the file's operating time to zero ticks
python Scripts/fe-nvram.py --set-ot 0 nvram.bin

# Change both values in a single operation
python Scripts/fe-nvram.py --set-sn 76189 --set-ot 0 nvram.bin
```

### [`fe-flash.py`](Scripts/fe-flash.py): Read or write Flash images using the bootloader of the device.

**Command switches:**

| Switch | Meaning |
| --- | --- |
| `--port PORT` | Serial port (required). |
| `--read` | Read both images. |
| `--write` | Erase, write, and verify both images. |
| `--lib FILE` | Library image path (default: `lib.bin`). |
| `--app FILE` | Application image path (default: `app.bin`). |
| `--allow-bulk-erase` | Required with `--write`; permits primary-Flash bulk erase. |
| `--backup-dir DIR` | Directory for automatic pre-write image backups (default: current directory). |
| `--timeout SECONDS` | UART response timeout (default: `2.0`). |
| `--boot-wait SECONDS` | Firmware transition timeout (default: `4.5`). |
| `--erase-timeout SECONDS` | Erase verification timeout (default: `120.0`). |
| `--write-delay SECONDS` | Delay after writing a block (default: `0.10`). |
| `--help` | Show built-in help. |

Select either `--read` or `--write`.

```sh
# Read both Flash images
python Scripts/fe-flash.py --port COM4 --read --lib lib.bin --app app.bin

# Write both images
python Scripts/fe-flash.py --port COM4 --write --lib lib.bin --app app.bin --allow-bulk-erase --backup-dir backups
```

## [Programmer](Programmer/)

#### A dev board based programmer for PSD813F1V with FE-5650A / FE-5680A memory map. Most likely you don't need it unless you have a desoldered PSD chip.

**[`fe-prog.hex`](Programmer/fe-prog.hex)** — pre-compiled firmware dump to upload to C8051F380 dev board.

**[`fe-prog.py`](Programmer/fe-prog.py)** — host-side command-line utility for the programmer. Numeric arguments are **hex** (without `0x`).

**Command switches:**

| Switch | Meaning |
| --- | --- |
| `-s PORT` | Serial port (required). |
| `-p PAGE` | PSD memory page (required). |
| `-f FILE` | Input image for writes or output file for reads. |
| `-rd ADDRESS,LENGTH` | Read data memory. |
| `-rp ADDRESS,LENGTH` | Read program memory. |
| `-wf ADDRESS,LENGTH` | Write Flash. |
| `-we ADDRESS,LENGTH` | Write data EEPROM. |
| `-wp ADDRESS,LENGTH` | Write program EEPROM. |
| `-c ADDRESS` | Erase a Flash sector. |
| `-h` | Show built-in help. |

Specify exactly one operation (`-rd`, `-rp`, `-wf`, `-we`, `-wp`, or `-c`). With `-rd` or `-rp`, `0,0` reads the complete 64 KiB address space. Reads and writes also require `-f`.

**Examples:**

```sh
# Read 1 KiB of data memory from page 0x80
python fe-prog.py -rd 2000,400 -p 80 -s COM3 -f nvram.bin

# Read 4 KiB of program memory
python fe-prog.py -rp 0,1000 -p 00 -s COM3 -f boot.bin

# Erase a sector and program the library image
python fe-prog.py -c 4000 -p 03 -s COM3
python fe-prog.py -wf 4000,4000 -p 03 -s COM3 -f lib.bin
```

## License and copyright

Copyright (C) 2026 ioccy.

Licensed under **GPL-3.0** with an additional attribution requirement under Section 7(b). See [LICENSE.md](LICENSE.md).

Original project: https://github.com/ioccy/fe-tools

Third-party materials retain their respective copyrights and licenses.
