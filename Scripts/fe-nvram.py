#!/usr/bin/env python3
"""DDS60 4.1 logical NVRAM image (1024 bytes) over application UART.

    py fe-nvram.py --read image.bin --port COM4
    py fe-nvram.py --write image.bin --port COM4
    py fe-nvram.py --show image.bin

The image is a reconstruction from application UART getters, not a raw EEPROM read.
In particular, 0x22 returns effective RAM DDS words; --read recovers NVRAM base
words only when their correction can be determined safely.
"""
import argparse
import struct
import sys
import time
from pathlib import Path

SIZE = 1024
DDS_LSB = 20_000_000 / 2**32
GETTERS = {0x65: b'\0', 0x57: b'\0', 0x59: b'\0'}
# (name, image offset, record length, getter, setter, marker)
FIELDS = [
    ('DDS configuration',             0x000,  8, 0x22, 0x21, None),
    ('Frequency correction table',    0x00A, 80, 0x59, 0x58, None),
    ('Sensor calibration thresholds', 0x064, 80, 0x57, 0x5D, None),
    ('Reference text',                0x0C8, 20, 0x2B, 0x2A, None),
    ('Serial number',                 0x12C, 20, 0x61, 0x60, None),
    ('Calibration point count',       0x15E,  1, 0x65, 0x64, None),
    ('Frequency offset',              0x168,  5, 0x2D, 0x2C, 0x55),
    ('Configuration',                 0x190,  4, 0x47, 0x46, 0x55),
    ('Operating counter',             0x1F4, 82, 0x67, None, 0x7A),
    ('User text 2',                   0x258, 35, 0x63, 0x62, None),
    ('User text 3',                   0x280, 10, 0x7A, 0x7B, None),
    ('User text 4',                   0x294, 10, 0x7C, 0x7D, None),
    ('User text 5',                   0x2A8, 10, 0x7E, 0x7F, None),
    ('Frequency limit',               0x2BC,  5, 0x3B, 0x3A, 0x67),
    ('Frequency parameter',           0x2C1,  5, 0x3D, 0x3C, 0x67),
]
TEXT_GETTERS = {0x2B, 0x61, 0x63, 0x7A, 0x7C, 0x7E}
EXPECTED = {0xF0: 32, 0x61: 20, 0x2B: 20, 0x63: 35,
            0x7A: 10, 0x7C: 10, 0x7E: 10}

def xor(data):
    result = 0
    for byte in data:
        result ^= byte
    return result


def frame(command, payload=b''):
    length = 4 + len(payload) + bool(payload)
    header = bytes((command, length & 255, length >> 8))
    return header + bytes((xor(header),)) + (payload + bytes((xor(payload),)) if payload else b'')


def read_exact(port, count, seconds=2.0):
    deadline = time.monotonic() + seconds
    result = bytearray()
    while len(result) < count and time.monotonic() < deadline:
        result.extend(port.read(count - len(result)))
    if len(result) != count:
        raise ValueError('UART response timeout')
    return bytes(result)


def receive(port, command, timeout=2.0):
    head = read_exact(port, 4, timeout)
    length = head[1] | head[2] << 8
    if head[0] != command or xor(head[:3]) != head[3] or length < 4 or length > 256 or length == 5:
        raise ValueError(f'Invalid UART header for 0x{command:02X}')
    body = read_exact(port, length - 4, timeout)
    if body and xor(body[:-1]) != body[-1]:
        raise ValueError(f'Invalid UART checksum for 0x{command:02X}')
    return body[:-1] if body else b''


def ascii_value(data):
    if not data or data[-1] != 0 or any(c < 32 or c > 126 for c in data[:-1]):
        raise ValueError('Invalid ASCII string')
    return data[:-1].decode('ascii')


def get(port, command):
    port.reset_input_buffer()
    packet = frame(command, GETTERS.get(command, b''))
    if port.write(packet) != len(packet):
        raise ValueError('UART transmit failed')
    port.flush()
    data = receive(port, command)
    if command in TEXT_GETTERS | {0xF0}:
        if len(data) > EXPECTED[command]:
            raise ValueError('Invalid UART text length')
        ascii_value(data)
    if command in (0x57, 0x59, 0x65):
        if not data or data[0] != 0:
            raise ValueError('Missing calibration selector echo')
        if len(data) != {0x57: 81, 0x59: 81, 0x65: 2}[command]:
            raise ValueError('Invalid calibration reply length')
    elif command in {0x22: 8, 0x47: 3, 0x67: 3, 0x53: 2, 0x2D: 4,
                     0x3B: 4, 0x3D: 4, 0x3E: 4}:
        if len(data) != {0x22: 8, 0x47: 3, 0x67: 3, 0x53: 2,
                         0x2D: 4, 0x3B: 4, 0x3D: 4, 0x3E: 4}[command]:
            raise ValueError(f'Unexpected 0x{command:02X} payload size')
    if command == 0x65 and not 1 <= data[1] <= 40:
        raise ValueError('Invalid calibration point count')
    return data


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def curve_correction(sensor, thresholds, corrections):
    """Firmware curve model: clamp endpoints, then float32 interpolate/truncate."""
    if len(thresholds) != len(corrections) or not thresholds:
        raise ValueError('Missing calibration curve')
    if len(thresholds) == 1:
        return corrections[0]
    descending = thresholds[0] > thresholds[-1]
    if thresholds[0] == thresholds[-1] or any(
        (a <= b if descending else a >= b) for a, b in zip(thresholds, thresholds[1:])
    ):
        raise ValueError('Invalid calibration curve ordering')
    if (sensor >= thresholds[0]) if descending else (sensor <= thresholds[0]):
        return corrections[0]
    if (sensor <= thresholds[-1]) if descending else (sensor >= thresholds[-1]):
        return corrections[-1]
    for x0, x1, y0, y1 in zip(thresholds, thresholds[1:], corrections, corrections[1:]):
        if x0 == sensor:
            return y0
        if x1 == sensor:
            return y1
        if min(x0, x1) < sensor < max(x0, x1):
            dx = f32(f32(sensor) - f32(x0))
            dy = f32(f32(y1) - f32(y0))
            width = f32(f32(x1) - f32(x0))
            return int(f32(f32(f32(dx * dy) / width) + f32(y0)))
    raise ValueError('Sensor value is outside the curve')


def recover_dds(port, replies):
    """Reject uncertain RAM->EEPROM DDS recovery; never back up effective 0x22."""
    flags = replies[0x47][0]
    if flags & 0x0C:
        raise ValueError('Cannot recover DDS base words while analog correction is enabled')
    before = get(port, 0x22)
    digital = int.from_bytes(get(port, 0x3E), 'big', signed=True)
    sample = get(port, 0x53)
    after = get(port, 0x22)
    if before != after:
        raise ValueError('DDS words changed during recovery')
    correction = 0
    if flags & 0x01:
        count = replies[0x65][1]
        temperature = bool(flags & 0x10)
        raw = int.from_bytes(sample, 'little')
        if not temperature and raw == 0xFFFF:
            raise ValueError('Sensor reading is unavailable')
        sensor = raw - 65536 if temperature and raw & 0x8000 else raw
        thresholds = [int.from_bytes(replies[0x57][i:i+2], 'little', signed=temperature)
                      for i in range(1, 1 + 2 * count, 2)]
        adjustments = [int.from_bytes(replies[0x59][i:i+2], 'little', signed=True)
                       for i in range(1, 1 + 2 * count, 2)]
        correction = curve_correction(sensor, thresholds, adjustments)
    total = digital + correction
    words = [((int.from_bytes(after[i:i+4], 'big') - total) & 0xFFFFFFFF)
             for i in (0, 4)]
    return b''.join(word.to_bytes(4, 'big') for word in words)


def check_firmware(port):
    if ascii_value(get(port, 0xF0)) != 'DDS60 4.1':
        raise ValueError('This tool requires DDS60 4.1 application firmware')


def counter_record_from_uart67(data):
    """Model the 82-byte operating counter after normal first-pass initialization."""
    if len(data) != 3:
        raise ValueError('0x67 response must contain slot, low byte, high byte')
    slot, low, high = data
    if slot >= 40:
        raise ValueError('Operating counter slot unavailable or invalid')
    record = bytearray(b'\xff' * 82)
    record[:2] = bytes((0x7A, slot))
    record[2:50] = b'\x00' * 48  # Slots 0–23 initialized to zero.
    for i in range(slot):
        record[2 + 2*i:4 + 2*i] = b'\xff\xff'  # Completed slots.
    p = 2 + 2*slot
    record[p:p+2] = bytes((high, low))  # EEPROM stores big-endian words.
    return bytes(record)


def make_image(port):
    check_firmware(port)
    # Get curve/config first so DDS recovery can use precisely the same values.
    replies = {command: get(port, command) for command in (0x47, 0x65, 0x57, 0x59)}
    dds = recover_dds(port, replies)
    image = bytearray(b'\xff' * SIZE)
    for name, offset, size, getter, setter, marker in FIELDS:
        if getter == 0x22:
            data = dds
        else:
            data = replies.get(getter)
            if data is None:
                data = get(port, getter)
            if getter in GETTERS:
                data = data[1:]  # Drop echoed calibration selector.
        if setter is None:
            image[offset:offset + size] = counter_record_from_uart67(data)
            continue
        if getter in TEXT_GETTERS:
            if data == b'\0':
                continue  # Empty strings are represented by an all-0xFF record.
            if len(data) > size:
                raise ValueError(name + ': string too long')
        elif len(data) != size - (marker is not None):
            raise ValueError(name + ': invalid response size')
        if marker is not None:
            image[offset] = marker
            offset += 1
        image[offset:offset + len(data)] = data
        time.sleep(0.05)
    return bytes(image)


def read_image(path):
    data = Path(path).read_bytes()
    if len(data) != SIZE:
        raise ValueError('NVRAM image must be exactly 1024 bytes')
    return data


def records_for_write(image):
    result = []
    for name, offset, size, getter, setter, marker in FIELDS:
        if setter is None:
            continue  # Counter wear-level history is not writable over UART.
        record = image[offset:offset + size]
        if marker is not None:
            if record[0] != marker:
                continue
            data = record[1:]
        elif getter in TEXT_GETTERS:
            if record[0] == 0xFF:
                continue
            end = record.find(b'\0')
            if end < 0:
                raise ValueError(name + ': unterminated string')
            data = record[:end + 1]
            ascii_value(data)
            if len(data) == 1:
                continue  # Empty strings are ambiguous in logical backup.
        else:
            if all(b == 0xFF for b in record):
                continue
            data = record
        if getter not in TEXT_GETTERS and len(data) != size - (marker is not None):
            raise ValueError(name + ': wrong image field size')
        if getter == 0x65 and not 1 <= data[0] <= 40:
            raise ValueError('Invalid calibration point count')
        if getter == 0x3D and int.from_bytes(data, 'big', signed=True) < 1:
            raise ValueError('Invalid offset divisor')
        if getter == 0x3B and not 1 <= int.from_bytes(data, 'big', signed=True) <= 0x19999999:
            raise ValueError('Invalid offset limit')
        if getter == 0x2D and abs(int.from_bytes(data, 'big', signed=True)) > 0x0FFFFFFF:
            raise ValueError('Invalid digital offset')
        result.append((name, getter, setter, data))
    offset = next((int.from_bytes(d, 'big', signed=True) for _, g, _, d in result if g == 0x2D), None)
    limit = next((int.from_bytes(d, 'big', signed=True) for _, g, _, d in result if g == 0x3B), None)
    if offset is not None and limit is not None and abs(offset) > limit:
        raise ValueError('Digital offset exceeds limit')
    if not result:
        raise ValueError('No writable NVRAM records')
    return result


def write_image(port, image):
    plan = records_for_write(image)  # Validate entire file before touching device.
    check_firmware(port)
    for name, getter, command, data in plan:
        port.reset_input_buffer()
        packet = frame(command, data)
        if port.write(packet) != len(packet):
            raise ValueError(name + ': UART transmit failed')
        port.flush()
        # Acknowledgements are optional. Consume one, if provided, before readback.
        try:
            ack = receive(port, command, 0.22)
        except ValueError as e:
            if str(e) != 'UART response timeout':
                raise ValueError(name + ': ' + str(e)) from e
        time.sleep(2.0)  # Allow nonvolatile storage to settle.
        observed = get(port, getter)
        if getter in GETTERS:
            observed = observed[1:]
        if observed != data:
            raise ValueError(name + ': write verification failed')


def field(image, offset, count, marker=None):
    record = image[offset:offset + count]
    return record if marker is None else (record[1:] if record[0] == marker else None)


def number(data):
    return int.from_bytes(data, 'big', signed=True)


def signed_hz(value):
    if value == 0:
        return '0.000 Hz'
    if abs(value) < 0.01:
        return f'{value * 1000:+,.3f} mHz'
    return f'{value:+,.3f} Hz'


def show(image):
    def section(title):
        print(f'\n{title}\n{"-" * len(title)}')
    def row(label, value):
        print(f'  {label:<28} {value}')
    def text(offset, size):
        record = image[offset:offset + size]
        if record[0] == 0xFF or b'\0' not in record:
            return 'N/A'
        try:
            return ascii_value(record[:record.index(0) + 1]) or '(empty)'
        except ValueError:
            return 'N/A'
    def flag(enabled):
        return 'Enabled' if enabled else 'Disabled'

    cfg = field(image, 0x190, 4, 0x55)
    flags = cfg[0] if cfg else 0
    temperature = bool(flags & 0x10)
    count = image[0x15E]
    thresholds = [int.from_bytes(image[0x64+i:0x66+i], 'little', signed=temperature)
                  for i in range(0, 80, 2)]
    corrections = [int.from_bytes(image[0x0A+i:0x0C+i], 'little', signed=True)
                   for i in range(0, 80, 2)]
    counter = image[0x1F4:0x246]

    print('DDS60 Device Information')
    section('Device info')
    row('Serial number', text(0x12C, 20))
    if counter[0] == 0x7A and counter[1] < 40:
        slot = counter[1]
        ticks = slot * 65536 + int.from_bytes(counter[2 + 2*slot:4 + 2*slot], 'big')
        row('Operating time', f'{ticks * 20 / 1440:,.2f} days')
    section('Calibration')
    if cfg:
        row('Calibration', flag(bool(flags & 0x01)) + ' (configured)')
        row('Calibration mode', 'Temperature' if temperature else 'Current')
        row('Sensor averaging', flag(bool(flags & 0x20)))
    if 1 <= count <= 40 and image[0x64:0x66] != b'\xff\xff':
        print()
        row('Calibration table', f'{count} active points')
        print()
        sensor_name = 'Package temperature' if temperature else 'Heater current'
        print(f'    {"Point":>5}  {sensor_name:>{len(sensor_name)}}    Correction')
        for i in range(count):
            value = f'{thresholds[i] * 0.5:,.1f} °C' if temperature else f'{thresholds[i] * 3.282563025:,.1f} mA'
            amount, unit = signed_hz(corrections[i] * DDS_LSB).rsplit(' ', 1)
            print(f'    {i + 1:>5}  {value:>{len(sensor_name)}}    {amount:>6} {unit}')
    section('Frequencies')
    raw_dds = image[:8]
    if raw_dds != b'\xff' * 8:
        a, b = int.from_bytes(raw_dds[:4], 'big'), int.from_bytes(raw_dds[4:], 'big')
        gap = (a - b) & 0xFFFFFFFF
        gap = min(gap, 2**32-gap)
        span = f'{gap * DDS_LSB / 2:,.3f}'.rstrip('0').rstrip('.')
        row('Configured DDS center', f'{(a + b) / 2 * DDS_LSB:,.3f} Hz')
        row('Configured DDS span', f'±{span} Hz')
    if cfg:
        print()
        row('Analog calibration', flag(bool(flags & 0x0C)))
    divisor = field(image, 0x2C1, 5, 0x67)
    offset = field(image, 0x168, 5, 0x55)
    limit = field(image, 0x2BC, 5, 0x67)
    scale = number(divisor) if divisor else 0
    if offset is not None and scale > 0:
        raw = number(offset)
        steps = (abs(raw) * 10 + 5) // scale
        row('Digital calibration offset', signed_hz((-steps if raw < 0 else steps) * DDS_LSB))
    if limit is not None and scale > 0:
        steps = (abs(number(limit)) * 10 + 5) // scale
        row('Offset limits', f'±{steps * DDS_LSB:,.3f} Hz')
    section('Misc')
    if cfg:
        selector = cfg[1]
        port_b = next((val for bit, val in ((1,0x20),(2,0x10),(4,0x31),(8,0x32),
                    (0x10,0x34),(0x20,0x38)) if selector & bit), 0)
        port_b |= (0x80 if flags & 0x02 else 0) | (0x40 if flags & 0x80 else 0)
        row('CPLD configutation', f'0x{port_b:02X}')
    for label, start, size in [('User text 1',0x0C8,20),('User text 2',0x258,35),
                              ('User text 3',0x280,10),('User text 4',0x294,10),
                              ('User text 5',0x2A8,10)]:
        row(label, text(start, size))


def main():
    parser = argparse.ArgumentParser(description='DDS60 4.1 NVRAM backup / restore / display', add_help=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--read', metavar='FILE')
    group.add_argument('--write', metavar='FILE')
    group.add_argument('--show', metavar='FILE')
    parser.add_argument('--port')
    args = parser.parse_args()
    if args.show:
        if args.port:
            parser.error('--show does not accept --port')
    elif not args.port:
        parser.error('--read and --write require --port')

    try:
        if args.show:
            show(read_image(args.show))
        else:
            import serial
            port = serial.Serial(port=None, baudrate=9600, timeout=0.1, write_timeout=2)
            port.dtr = False
            port.rts = False
            port.port = args.port
            with port:
                if args.read:
                    # Only create/replace file once the complete reconstruction succeeded.
                    Path(args.read).write_bytes(make_image(port))
                else:
                    write_image(port, read_image(args.write))
        return 0
    except Exception as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
