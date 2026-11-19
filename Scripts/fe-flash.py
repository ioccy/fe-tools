#!/usr/bin/env python3
"""DDS60 / DDS60FL UART Flash transfer tool (9600 8N1).

Flash images:
    lib: 0x4000..0x7FFF (16 KiB), UART Flash blocks 0x0080..0x00FF
    app: 0x8000..0xBFFF (16 KiB), UART Flash blocks 0x0000..0x007F

The ranges were dumped with PSD page 0x03; the bootloader's block-to-Flash
mapping selects the physical Flash window (no host-side PSD page command).

After successful --read/--write, a verified read of block 0x0010 restores
P1.7's output latch before BOOT 0x90 starts the application.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BLOCK_SIZE = 128
IMAGE_SIZE = 0x4000
BAUD = 9600

CMD_WRITE = 0x80
CMD_READ = 0x81
CMD_ERASE = 0x82
CMD_CONTINUE = 0x90
CMD_VERSION = 0xF0
CMD_STOP = 0xF1

# The bootloader's 0x81 block 0x0010 path restores the P1.7 output latch.
P17_RESTORE_BLOCK = 0x0010

# Preserve the original command-line defaults.
DEFAULT_LIB = "lib.bin"
DEFAULT_APP = "app.bin"


class ProtocolError(RuntimeError):
    """Unexpected UART response, invalid checksums, or failed verification."""


class BytePort(Protocol):
    def read(self, size: int = 1) -> bytes: ...
    def write(self, data: bytes) -> int | None: ...
    def flush(self) -> None: ...
    def reset_input_buffer(self) -> None: ...


@dataclass(frozen=True)
class Area:
    name: str
    start: int
    first_block: int

    @property
    def blocks(self) -> range:
        return range(self.first_block, self.first_block + IMAGE_SIZE // BLOCK_SIZE)


LIB = Area("lib", 0x4000, 0x0080)
APP = Area("app", 0x8000, 0x0000)
AREAS = (LIB, APP)


def xor_bytes(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
    return value


def frame(command: int, payload: bytes = b"") -> bytes:
    """[command, total length LE16, header XOR, payload, payload XOR]."""
    if not 0 <= command <= 255:
        raise ValueError("Invalid UART command")
    length = 4 + (len(payload) + 1 if payload else 0)
    if length > 0xFFFF:
        raise ValueError("UART frame too long")
    header = bytes((command, length & 255, length >> 8))
    return header + bytes((xor_bytes(header),)) + (
        payload + bytes((xor_bytes(payload),)) if payload else b""
    )


def block_payload(block: int) -> bytes:
    if not 0 <= block <= 0xFFFF:
        raise ValueError(f"Block number out of range: {block}")
    return block.to_bytes(2, "little")


def identify(version: str) -> str | None:
    # The longer prefix must be tested first.
    if version.startswith("DDS60FL"):
        return "bootloader"
    if version.startswith("DDS60"):
        return "application"
    return None


def decode_version(payload: bytes) -> str:
    # F0 is an ASCII, NUL-terminated firmware identifier.
    if not payload.endswith(b"\x00") or payload.count(b"\x00") != 1:
        raise ProtocolError(f"Malformed F0 firmware version field: {payload!r}")
    return payload[:-1].decode("ascii", errors="replace")


class BootLink:
    def __init__(self, port: BytePort, *, response_timeout: float = 2.0,
                 boot_wait: float = 4.5, write_delay: float = 0.10):
        self.port = port
        self.response_timeout = response_timeout
        self.boot_wait = boot_wait
        self.write_delay = write_delay

    def _send(self, command: int, payload: bytes = b"") -> None:
        packet = frame(command, payload)
        written = self.port.write(packet)
        if written is not None and written != len(packet):
            raise ProtocolError(f"Short UART write: {written}/{len(packet)}")
        self.port.flush()

    def _read_exact(self, count: int, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        data = bytearray()
        while len(data) < count:
            if time.monotonic() >= deadline:
                raise ProtocolError(f"UART timeout: received {len(data)}/{count} bytes")
            part = self.port.read(count - len(data))
            if part:
                data.extend(part)
            else:
                time.sleep(0.004)
        return bytes(data)

    def _receive(self, command: int, *, timeout: float | None = None,
                 expected_payload_size: int | None = None) -> bytes:
        timeout = self.response_timeout if timeout is None else timeout
        # Time budget applies to the whole response, including 128 data bytes.
        started = time.monotonic()
        header = self._read_exact(4, timeout)
        if header[0] != command:
            raise ProtocolError(
                f"Unexpected UART reply command 0x{header[0]:02X}, expected 0x{command:02X}"
            )
        if xor_bytes(header[:3]) != header[3]:
            raise ProtocolError(f"Invalid 0x{command:02X} reply header XOR")
        length = int.from_bytes(header[1:3], "little")
        if not 4 <= length <= 1024 or length == 5:
            raise ProtocolError(f"Invalid 0x{command:02X} reply length {length}")
        if expected_payload_size is not None:
            expected_length = 4 if expected_payload_size == 0 else 5 + expected_payload_size
            if length != expected_length:
                raise ProtocolError(
                    f"0x{command:02X} response length {length}, expected {expected_length}"
                )
        remaining = max(0.01, timeout - (time.monotonic() - started))
        body = self._read_exact(length - 4, remaining)
        if length == 4:
            return b""
        if xor_bytes(body[:-1]) != body[-1]:
            raise ProtocolError(f"Invalid 0x{command:02X} reply payload XOR")
        return body[:-1]

    def _query(self, command: int, payload: bytes = b"",
               *, expected_payload_size: int | None = None) -> bytes:
        self.port.reset_input_buffer()  # no stale response before an exchange
        self._send(command, payload)
        return self._receive(command, expected_payload_size=expected_payload_size)

    def firmware(self) -> tuple[str, str]:
        value = decode_version(self._query(CMD_VERSION))
        stage = identify(value)
        if stage is None:
            raise ProtocolError(f"Unrecognized firmware string: {value!r}")
        return stage, value

    def wait_for_stage(self, expected: str, seconds: float) -> str:
        deadline = time.monotonic() + seconds
        error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                stage, version = self.firmware()
                if stage == expected:
                    return version
                if stage not in ("application", "bootloader"):
                    raise ProtocolError(f"Unknown stage {stage}")
                error = ProtocolError(f"Received {stage} ({version}) instead of {expected}")
            except ProtocolError as ex:
                # Brief UART silence is normal while firmware changes, but a
                # malformed/unknown reply is not evidence of a valid stage.
                if "timeout" not in str(ex).lower():
                    raise
                error = ex
            if time.monotonic() < deadline:
                time.sleep(0.12)
        raise ProtocolError(f"Expected {expected}; last reply: {error}")

    def enter_and_stop_bootloader(self) -> None:
        stage, version = self.firmware()
        print(f"Detected {stage}: {version}")
        if stage == "application":
            print("Entering EEPROM bootloader (APP F1)...")
            # APP F1 is a silent transition, NOT a framed acknowledgement.
            self._send(CMD_STOP)
            print("Bootloader:", self.wait_for_stage("bootloader", self.boot_wait))
        # BOOT F1 is a different handler: stop automatic application launch.
        print("Stopping automatic boot (BOOT F1)...")
        self.port.reset_input_buffer()
        self._send(CMD_STOP)
        self._receive(CMD_STOP, expected_payload_size=0)  # ACK is an empty frame
        stage, version = self.firmware()
        if stage != "bootloader":
            raise ProtocolError(f"BOOT F1 failed to hold loader: {version}")
        print(f"Bootloader held: {version}")

    def read_block(self, block: int) -> bytes:
        # Example: 81 07 00 86 10 00 10 for block 0x0010.
        return self._query(CMD_READ, block_payload(block), expected_payload_size=BLOCK_SIZE)

    def write_block(self, block: int, data: bytes) -> None:
        if len(data) != BLOCK_SIZE:
            raise ValueError("Write block must contain exactly 128 bytes")
        # No UART ACK for BOOT 0x80. Verify using BOOT 0x81.
        self._send(CMD_WRITE, block_payload(block) + data)

    def erase_all(self) -> None:
        # BOOT 0x82 is *bulk* erase; there is no sector-erase UART command.
        # No UART ACK; the caller verifies erasure through readback.
        self._send(CMD_ERASE)

    def continue_application(self) -> str:
        # A completed BOOT 81 read restores P1.7's output latch. Validate
        # its complete 133-byte response before BOOT 90 is allowed.
        stage, version = self.firmware()
        if stage != "bootloader":
            raise ProtocolError(f"Refusing BOOT 90: expected loader, got {version}")
        self.read_block(P17_RESTORE_BLOCK)
        stage, version = self.firmware()
        if stage != "bootloader":
            raise ProtocolError(f"Refusing BOOT 90: loader changed after block read ({version})")
        self._send(CMD_CONTINUE)  # BOOT 90 has no ACK
        version = self.wait_for_stage("application", self.boot_wait)
        print(f"Application running: {version}")
        return version


def read_area(link: BootLink, area: Area) -> bytes:
    buffer = bytearray()
    for i, block in enumerate(area.blocks, start=1):
        buffer.extend(link.read_block(block))
        if i % 16 == 0:
            print(f"  {area.name}: read {i}/128 blocks")
    if len(buffer) != IMAGE_SIZE:
        raise ProtocolError(f"Wrong {area.name} image size: {len(buffer)}")
    return bytes(buffer)


def atomic_write(path: Path, data: bytes) -> None:
    """Atomically create or replace a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".fe-flash-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def get_images(lib_path: Path, app_path: Path) -> dict[str, bytes]:
    images = {"lib": lib_path.read_bytes(), "app": app_path.read_bytes()}
    for name, content in images.items():
        if len(content) != IMAGE_SIZE:
            raise ValueError(
                f"{name} input must contain exactly 0x4000 bytes; found 0x{len(content):X}"
            )
    return images


def await_bulk_erase(link: BootLink, timeout: float = 120.0) -> None:
    """Wait until *every* target block reads erased, tolerating erase latency."""
    deadline = time.monotonic() + timeout
    last = "no reply"
    while time.monotonic() < deadline:
        try:
            verify_erase(link)
            return
        except ProtocolError as ex:
            last = str(ex)
        if time.monotonic() < deadline:
            time.sleep(0.7)
    raise ProtocolError(f"Flash bulk-erase deadline reached: {last}")


def verify_erase(link: BootLink) -> None:
    print("Checking bulk erase in the two target areas...")
    for area in AREAS:
        for i, block in enumerate(area.blocks, start=1):
            found = link.read_block(block)
            if found != bytes((0xFF,)) * BLOCK_SIZE:
                raise ProtocolError(
                    f"Erase check failed in {area.name} block 0x{block:04X} "
                    f"(address 0x{area.start + (i - 1) * BLOCK_SIZE:04X})"
                )
        print(f"  {area.name}: erased 128/128 blocks")


def program_images(link: BootLink, images: dict[str, bytes]) -> None:
    blank = b"\xFF" * BLOCK_SIZE
    for area in AREAS:
        data = images[area.name]
        written = 0
        for i, block in enumerate(area.blocks):
            piece = data[i * BLOCK_SIZE:(i + 1) * BLOCK_SIZE]
            if piece != blank:
                link.write_block(block, piece)
                # The write operation has no ACK and may still be executing.
                time.sleep(link.write_delay)
                written += 1
            actual = link.read_block(block)
            if actual != piece:
                # Retrying a READ is safe; never repeat the Flash write.
                time.sleep(max(0.2, link.write_delay))
                actual = link.read_block(block)
            if actual != piece:
                offset = next(j for j in range(BLOCK_SIZE) if piece[j] != actual[j])
                address = area.start + i * BLOCK_SIZE + offset
                raise ProtocolError(
                    f"Verification failed: {area.name} address 0x{address:04X}, "
                    f"block 0x{block:04X}, expected 0x{piece[offset]:02X}, "
                    f"got 0x{actual[offset]:02X}"
                )
            if (i + 1) % 16 == 0:
                print(f"  {area.name}: verified {i + 1}/128 blocks")
        print(f"  {area.name}: complete ({written} programmed, {128-written} blank)")
    # A second pass also detects later writes changing earlier blocks.
    print("Final full readback verification...")
    for area in AREAS:
        expected = images[area.name]
        for i, block in enumerate(area.blocks):
            actual = link.read_block(block)
            want = expected[i * BLOCK_SIZE:(i + 1) * BLOCK_SIZE]
            if actual != want:
                index = next(j for j in range(BLOCK_SIZE) if actual[j] != want[j])
                address = area.start + i * BLOCK_SIZE + index
                raise ProtocolError(f"Final verification failed: {area.name} "
                                    f"at 0x{address:04X} (block 0x{block:04X})")
        print(f"  {area.name}: {IMAGE_SIZE} bytes verified")


def do_read(link: BootLink, lib_path: Path, app_path: Path) -> None:
    # Read both areas before replacing either destination file.
    lib = read_area(link, LIB)
    app = read_area(link, APP)
    atomic_write(lib_path, lib)
    atomic_write(app_path, app)
    print(f"Saved lib: {lib_path} ({len(lib):#x} bytes)")
    print(f"Saved app: {app_path} ({len(app):#x} bytes)")


def do_write(link: BootLink, lib_path: Path, app_path: Path,
             *, backup_parent: Path, erase_timeout: float = 120.0) -> Path:
    images = get_images(lib_path, app_path)  # validate before touching Flash
    print("Reading both existing areas before bulk erase...")
    previous = {area.name: read_area(link, area) for area in AREAS}
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(
        prefix="fe-flash-backup-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + "-",
        dir=str(backup_parent),
    ))
    for area in AREAS:
        atomic_write(backup / f"{area.name}.bin", previous[area.name])
    print(f"Pre-erase backup saved to {backup}")
    print("Erasing Flash (BOOT 82: bulk erase)...")
    link.erase_all()
    await_bulk_erase(link, timeout=erase_timeout)
    print("Programming and verifying blocks...")
    program_images(link, images)
    return backup


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fe-flash.py",
        description="Read or write DDS60 lib/app Flash via EEPROM bootloader UART.",
    )
    p.add_argument("--port", required=True, help="Serial port (e.g. COM3 or /dev/ttyUSB0)")
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--read", action="store_true", help="Read both Flash areas into .bin files")
    action.add_argument("--write", action="store_true", help="Bulk erase, write both images, verify")
    p.add_argument("--lib", type=Path, default=Path(DEFAULT_LIB), help="16 KiB lib .bin path")
    p.add_argument("--app", type=Path, default=Path(DEFAULT_APP), help="16 KiB app .bin path")
    p.add_argument("--allow-bulk-erase", action="store_true",
                   help="Required for --write: BOOT 82 erases the full primary Flash")
    p.add_argument("--backup-dir", type=Path, default=Path("."),
                   help="Parent folder for automatic pre-erase backups")
    p.add_argument("--timeout", type=float, default=2.0,
                   help="UART frame response deadline in seconds (default 2.0)")
    p.add_argument("--boot-wait", type=float, default=4.5,
                   help="Firmware transition deadline in seconds (default 4.5)")
    p.add_argument("--erase-timeout", type=float, default=120.0,
                   help="Bulk erase verification deadline in seconds (default 120)")
    p.add_argument("--write-delay", type=float, default=0.10,
                   help="Post-write settle delay in seconds (default 0.10)")
    return p


def main(argv: list[str] | None = None, *, port_factory=None) -> int:
    args = parser().parse_args(argv)
    if args.lib.resolve() == args.app.resolve():
        parser().error("--lib and --app must refer to different files")
    if args.write and not args.allow_bulk_erase:
        parser().error("--write requires --allow-bulk-erase (BOOT 82 erases all primary Flash sectors)")
    if (args.timeout <= 0 or args.boot_wait <= 0 or args.erase_timeout <= 0
            or args.write_delay < 0):
        parser().error("timeouts must be positive and --write-delay nonnegative")
    if args.write:
        # Fail before opening the port if either image is missing or malformed.
        get_images(args.lib, args.app)

    if port_factory is None:
        try:
            import serial
        except ImportError as ex:
            raise RuntimeError("Install pyserial: python -m pip install pyserial") from ex
        def port_factory(name):
            # Set control lines *before* opening the port, as in the original
            # implementation. A particular USB adapter may still pulse them.
            port = serial.serial_for_url(
                name, baudrate=BAUD, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0.05, write_timeout=5.0, xonxoff=False,
                rtscts=False, dsrdtr=False, do_not_open=True,
            )
            port.dtr = False
            port.rts = False
            port.open()
            return port

    port = port_factory(args.port)
    try:
        # Disable hardware-control outputs, consistent with DDS60 UART setup.
        if hasattr(port, "dtr"):
            port.dtr = False
        if hasattr(port, "rts"):
            port.rts = False
        link = BootLink(port, response_timeout=args.timeout,
                        boot_wait=args.boot_wait, write_delay=args.write_delay)
        link.enter_and_stop_bootloader()
        if args.read:
            do_read(link, args.lib, args.app)
        else:
            do_write(link, args.lib, args.app, backup_parent=args.backup_dir,
                     erase_timeout=args.erase_timeout)
        # Success path only: restore P1.7, BOOT 90, confirm application.
        print("Restoring P1.7 and continuing application boot...")
        link.continue_application()
        print("Done.")
        return 0
    finally:
        if hasattr(port, "close"):
            port.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
