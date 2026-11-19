#!/usr/bin/env python3
"""
fe-prog.py - host tool for the PSD813F1V serial programmer (C8051F380 firmware).

Serial link: 115200 8N1. The device prints a "> " prompt when it is ready for a
command, echoes everything it receives and never reports errors. All numbers
on the wire and on the command line are hex.

Device commands used (each one is terminated with '\\r'):
    P  PAGE            set memory page
    RD ADDRESS LENGTH  read data memory      (0 0 = whole 0000..FFFF space)
    RP ADDRESS LENGTH  read program memory   (0 0 = whole 0000..FFFF space)
    WF ADDRESS LENGTH  write flash           (each byte is echoed back)
    WE ADDRESS LENGTH  write data EEPROM     (each byte is echoed back)
    WP ADDRESS LENGTH  write program EEPROM  (each byte is echoed back)
    C  ADDRESS         erase flash           (prompt returns when done)

Requires pyserial:  pip install pyserial
"""

import argparse
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is required: pip install pyserial")

BAUD = 115200
PROMPT = b"> "
EOL = b"\r\n"
FULL_SPACE = 0x10000        # 0000..FFFF

# Timeouts, seconds
T_SYNC = 1.5                # wait for prompt after the start-up '\r'
T_ECHO = 2.0                # wait for the command echo
T_PROMPT = 2.0              # wait for a prompt after a short command
T_IDLE = 3.0                # max silence while receiving read data
T_BYTE = 5.0                # wait for the echo of one written byte
T_WRITE_END = 5.0           # wait for the prompt after the last written byte
T_ERASE = 60.0              # wait for the prompt after an erase
SYNC_TRIES = 3

# option -> (kind, serial command, description)
OPS = {
    "rd": ("read", "RD", "data memory"),
    "rp": ("read", "RP", "program memory"),
    "wf": ("write", "WF", "flash"),
    "we": ("write", "WE", "data EEPROM"),
    "wp": ("write", "WP", "program EEPROM"),
}

EPILOG = """examples:
  fe-prog.py -rd 0,0 -p AA -f dump.bin -s COM6
  fe-prog.py -wf 8000,800 -p 80 -f c:\\mydir\\dump.bin -s COM6
  fe-prog.py -c 4000 -p 00 -s COM6

ADDRESS and LENGTH are 0..FFFF, PAGE is 00..FF (all hex). For -rd/-rp,
0,0 reads the whole address space (65536 bytes).
"""


class PsdError(Exception):
    pass


def hx(value, digits=4):
    return f"0x{value:0{digits}X}"


# ---------------------------------------------------------------- console --

_line_open = False          # the status line is displayed and not yet terminated


def begin_line(text):
    """Start the one and only status line (no line break)."""
    global _line_open
    sys.stdout.write(text)
    sys.stdout.flush()
    _line_open = True


def end_progress_line(suffix=""):
    """Terminate the status line (if there is one), optionally appending suffix."""
    global _line_open
    if _line_open:
        sys.stdout.write(suffix + "\n")
        sys.stdout.flush()
        _line_open = False


class Progress:
    """Redraws '<prefix>: <done> / <total> bytes' in place on the status line."""

    def __init__(self, prefix, total):
        self.prefix = prefix
        self.total = total
        self.last = 0.0

    def update(self, done, force=False):
        global _line_open
        now = time.monotonic()
        if force or now - self.last >= 0.2:
            self.last = now
            sys.stdout.write(f"\r{self.prefix}: {hx(done)} / {hx(self.total)} bytes")
            sys.stdout.flush()
            _line_open = True

    def finish(self, done):
        self.update(done, force=True)
        end_progress_line()


# ----------------------------------------------------------------- device --

class Device:
    def __init__(self, port):
        try:
            self.ser = serial.Serial(
                port=port, baudrate=BAUD, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0.05, write_timeout=5)
        except (serial.SerialException, OSError, ValueError) as exc:
            raise PsdError(f"Cannot open {port}: {exc}") from exc
        self.buf = bytearray()      # received but not yet consumed bytes
        time.sleep(0.1)

    def close(self):
        self.ser.close()

    # -- low level receive helpers --

    def _fill(self):
        chunk = self.ser.read(self.ser.in_waiting or 1)
        self.buf += chunk
        return len(chunk)

    def flush_input(self):
        self.ser.reset_input_buffer()
        self.buf.clear()

    def read_until(self, token, timeout):
        """Consume everything up to and including token; None on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            pos = self.buf.find(token)
            if pos >= 0:
                end = pos + len(token)
                data = bytes(self.buf[:end])
                del self.buf[:end]
                return data
            if time.monotonic() >= deadline:
                return None
            self._fill()

    def read_exact(self, count, idle_timeout, progress=None):
        """Read count bytes; gives up after idle_timeout seconds of silence."""
        out = bytearray()
        last = time.monotonic()
        while len(out) < count:
            if self.buf:
                take = min(count - len(out), len(self.buf))
                out += self.buf[:take]
                del self.buf[:take]
                last = time.monotonic()
                if progress:
                    progress.update(len(out))
            elif not self._fill() and time.monotonic() - last > idle_timeout:
                break
        return bytes(out)

    # -- protocol --

    def sync(self):
        """Send '\\r' until the device answers with a '> ' prompt."""
        for _ in range(SYNC_TRIES):
            self.flush_input()
            self.ser.write(b"\r")
            self.ser.flush()
            if self.read_until(PROMPT, T_SYNC) is not None:
                return
        raise PsdError(f"Device did not answer with a '> ' prompt "
                       f"({SYNC_TRIES} attempts)")

    def command(self, text):
        """Send a command line and consume its echo (up to and including CR LF)."""
        raw = text.encode("ascii")
        self.flush_input()
        self.ser.write(raw + b"\r")
        self.ser.flush()
        echo = self.read_until(EOL, T_ECHO)
        if echo is None:
            raise PsdError(f"No command echo received (got {bytes(self.buf)!r})")
        if not echo[:-len(EOL)].endswith(raw):
            raise PsdError(f"Unexpected command echo: sent {text!r}, got {echo!r}")

    def wait_prompt(self, timeout, what, fatal=True):
        if self.read_until(PROMPT, timeout) is None:
            if fatal:
                raise PsdError(f"Timeout waiting for the '> ' prompt ({what})")
            end_progress_line()
            print(f"Warning: no '> ' prompt after {what}", file=sys.stderr)

    def set_page(self, page):
        self.command(f"P {page:X}")
        self.wait_prompt(T_PROMPT, "page select")

    def send_byte(self, value, where):
        """Send one byte and wait for the device to echo it back."""
        self.ser.write(bytes([value]))
        echo = self.read_exact(1, T_BYTE)
        if not echo:
            raise PsdError(f"No echo for byte {hx(value, 2)} at address {hx(where)}")
        if echo[0] != value:
            raise PsdError(f"Echo mismatch at address {hx(where)}: "
                           f"sent {hx(value, 2)}, got {hx(echo[0], 2)}")


# ------------------------------------------------------------- operations --

def do_read(dev, job):
    addr, length = job["addr"], job["length"]
    progress = Progress(f"Reading {job['label']} from {hx(addr)} "
                        f"page {hx(job['page'], 2)} to [{job['file']}]", length)
    progress.update(0, force=True)
    dev.command(f"{job['cmd']} {addr:X} {job['wire_length']:X}")
    data = dev.read_exact(length, T_IDLE, progress)
    progress.finish(len(data))
    if len(data) != length:
        raise PsdError(f"Received {len(data)} bytes instead of {length}")
    dev.wait_prompt(T_PROMPT, "read", fatal=False)
    try:
        with open(job["file"], "wb") as fh:
            fh.write(data)
    except OSError as exc:
        raise PsdError(f"Cannot write {job['file']}: {exc}") from exc


def do_write(dev, job):
    addr, length, data = job["addr"], job["length"], job["data"]
    progress = Progress(f"Writing {job['label']} to {hx(addr)} "
                        f"page {hx(job['page'], 2)} from [{job['file']}]", length)
    progress.update(0, force=True)
    dev.command(f"{job['cmd']} {addr:X} {length:X}")
    for i, value in enumerate(data):
        dev.send_byte(value, addr + i)
        progress.update(i + 1)
    progress.finish(length)
    dev.wait_prompt(T_WRITE_END, "last byte", fatal=False)


def do_erase(dev, job):
    begin_line(f"Erasing flash at {hx(job['addr'])} page {hx(job['page'], 2)}...")
    dev.command(f"C {job['addr']:X}")
    dev.wait_prompt(T_ERASE, "erase")
    end_progress_line(" ok")


def execute(args, job):
    dev = Device(args.s)
    try:
        dev.sync()
        dev.set_page(args.p)
        {"read": do_read, "write": do_write, "erase": do_erase}[job["kind"]](dev, job)
    finally:
        dev.close()


# --------------------------------------------------------------- arguments --

def hex_value(text, name, maxval):
    try:
        value = int(text.strip(), 16)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{name} must be a hex number, got {text!r}")
    if not 0 <= value <= maxval:
        raise argparse.ArgumentTypeError(
            f"{name} must be in range 0x0..0x{maxval:X}, got {text!r}")
    return value


def page_type(text):
    return hex_value(text, "PAGE", 0xFF)


def addr_type(text):
    return hex_value(text, "ADDRESS", 0xFFFF)


def pair_type(text):
    parts = text.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"expected ADDRESS,LENGTH (hex), got {text!r}")
    return (hex_value(parts[0], "ADDRESS", 0xFFFF),
            hex_value(parts[1], "LENGTH", 0xFFFF))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fe-prog.py", allow_abbrev=False,
        description="PSD813F1V serial programmer (115200 8N1). All numbers are hex.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", metavar="COM_PORT", required=True,
                        help="serial port, e.g. COM6 (obligatory)")
    parser.add_argument("-p", metavar="PAGE", type=page_type, required=True,
                        help="memory page 00..FF (obligatory, used with every operation)")
    parser.add_argument("-f", metavar="FILENAME",
                        help="file name or full path (read output / write input)")
    ops = parser.add_mutually_exclusive_group(required=True)
    ops.add_argument("-rd", metavar="ADDRESS,LENGTH", type=pair_type,
                     help="read data memory (0,0 = whole space)")
    ops.add_argument("-rp", metavar="ADDRESS,LENGTH", type=pair_type,
                     help="read program memory (0,0 = whole space)")
    ops.add_argument("-wf", metavar="ADDRESS,LENGTH", type=pair_type,
                     help="write flash")
    ops.add_argument("-we", metavar="ADDRESS,LENGTH", type=pair_type,
                     help="write data EEPROM")
    ops.add_argument("-wp", metavar="ADDRESS,LENGTH", type=pair_type,
                     help="write program EEPROM")
    ops.add_argument("-c", metavar="ADDRESS", type=addr_type,
                     help="erase flash")
    return parser


def prepare(parser, args):
    """Validate everything that can be checked before touching the port."""
    key = next(k for k in (*OPS, "c") if getattr(args, k) is not None)

    if key == "c":
        return {"kind": "erase", "addr": args.c, "page": args.p}

    kind, cmd, label = OPS[key]
    addr, length = getattr(args, key)
    whole = False
    if length == 0:
        if kind == "read" and addr == 0:
            length, whole = FULL_SPACE, True
        elif kind == "read":
            parser.error(f"-{key}: LENGTH 0 (whole address space) requires ADDRESS 0")
        else:
            parser.error(f"-{key}: LENGTH must not be 0")
    if addr + length - 1 > 0xFFFF:
        parser.error(f"-{key}: ADDRESS + LENGTH - 1 = {hx(addr + length - 1)} "
                     f"exceeds 0xFFFF")
    if args.f is None:
        parser.error(f"-f FILENAME is required with -{key}")

    job = {"kind": kind, "cmd": cmd, "label": label, "addr": addr,
           "length": length, "whole": whole,
           "wire_length": 0 if whole else length, "file": args.f,
           "page": args.p}

    if kind == "read":
        folder = os.path.dirname(os.path.abspath(args.f))
        if not os.path.isdir(folder):
            parser.error(f"-f: directory does not exist: {folder}")
    else:
        try:
            size = os.path.getsize(args.f)
            with open(args.f, "rb") as fh:
                data = fh.read(length)
        except OSError as exc:
            parser.error(f"-f: cannot read {args.f}: {exc}")
        if len(data) < length:
            parser.error(f"-f: file has {size} bytes, {length} requested "
                         f"({hx(length)})")
        job["data"] = data
    return job


def main():
    parser = build_parser()
    args = parser.parse_args()
    job = prepare(parser, args)
    try:
        execute(args, job)
    except PsdError as exc:
        end_progress_line()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except serial.SerialException as exc:
        end_progress_line()
        print(f"Serial port error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        end_progress_line()
        print("Interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
