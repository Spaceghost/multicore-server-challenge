#!/usr/bin/env python3
"""Offline differential packet tests. No sockets, BPF syscalls, or interfaces."""
import ctypes
from pathlib import Path
import random
import struct
import sys

library = ctypes.CDLL(str(Path(sys.argv[1]).resolve()))
action = library.nc_offline_action
action.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint16,
                   ctypes.c_uint32, ctypes.c_int]
action.restype = ctypes.c_int


def expected(packet, port, queue, mapped):
    if not port or len(packet) < 14:
        return 2
    protocol = int.from_bytes(packet[12:14], "big")
    cursor = 14
    for _ in range(2):
        if protocol not in (0x8100, 0x88A8):
            break
        if len(packet) < cursor + 4:
            return 2
        protocol = int.from_bytes(packet[cursor + 2:cursor + 4], "big")
        cursor += 4
    if protocol != 0x0800 or len(packet) < cursor + 20:
        return 2
    ip = packet[cursor:]
    ihl = (ip[0] & 15) * 4
    total = int.from_bytes(ip[2:4], "big")
    fragment = int.from_bytes(ip[6:8], "big")
    if (ip[0] >> 4 != 4 or ip[9] != 6 or ihl < 20 or len(ip) < ihl
            or fragment & 0x3FFF or total < ihl + 20 or len(ip) < total):
        return 2
    tcp = ip[ihl:total]
    tcp_header = (tcp[12] >> 4) * 4
    if tcp_header < 20 or tcp_header > len(tcp):
        return 2
    destination = int.from_bytes(tcp[2:4], "big")
    return 4 if destination == port and mapped and queue < 64 else 2


checks = 0


def check(packet, port=3000, queue=0, mapped=1):
    global checks
    # A generous backing allocation also makes all packet pointer arithmetic
    # well-defined in native C even when a declared IP total exceeds the frame.
    buffer = ctypes.create_string_buffer(131072)
    buffer[:len(packet)] = packet
    actual = action(buffer, len(packet), port, queue, mapped)
    want = expected(packet, port, queue, mapped)
    if actual != want:
        raise AssertionError(f"actual={actual} expected={want} port={port} queue={queue} mapped={mapped} packet={packet.hex()}")
    checks += 1


def frame(port=3000, vlan_tags=(), ihl=20, tcp_header=20, payload=b"", fragment=0):
    ethernet = b"\xaa" * 6 + b"\xbb" * 6
    for protocol in vlan_tags:
        ethernet += struct.pack("!HH", protocol, 42)
    ethernet += struct.pack("!H", 0x0800)
    ip = bytearray(ihl)
    ip[0] = 0x40 | (ihl // 4)
    ip[2:4] = struct.pack("!H", ihl + tcp_header + len(payload))
    ip[6:8] = struct.pack("!H", fragment)
    ip[8:10] = bytes([64, 6])
    tcp = bytearray(tcp_header)
    tcp[:4] = struct.pack("!HH", 12345, port)
    tcp[12] = (tcp_header // 4) << 4
    return ethernet + ip + tcp + payload


for tags in [(), (0x8100,), (0x88A8,), (0x88A8, 0x8100), (0x8100, 0x8100),
             (0x8100, 0x8100, 0x8100)]:
    for ihl in [20, 24, 60]:
        for tcp_header in [20, 24, 60]:
            packet = frame(vlan_tags=tags, ihl=ihl, tcp_header=tcp_header, payload=b"GET / HTTP/1.1\r\n\r\n")
            for size in range(len(packet) + 1):
                check(packet[:size])
            for port in [0, 80, 3000, 65535]:
                for queue in [0, 63, 64, 0xFFFFFFFF]:
                    for mapped in [0, 1]:
                        check(packet, port, queue, mapped)

for fragment in [1, 8191, 0x2000, 0x2001, 0x4000]:
    check(frame(fragment=fragment))
for ethernet_type in [0x0806, 0x86DD, 0x0800, 0xFFFF]:
    packet = bytearray(frame())
    packet[12:14] = struct.pack("!H", ethernet_type)
    check(bytes(packet))
for version_ihl in [0, 0x40, 0x44, 0x45, 0x4F, 0x65]:
    packet = bytearray(frame())
    packet[14] = version_ihl
    check(bytes(packet))
for total in [0, 1, 19, 20, 39, 40, 41, 65535]:
    packet = bytearray(frame())
    packet[16:18] = struct.pack("!H", total)
    check(bytes(packet))
for tcp_size in [0, 0x40, 0x50, 0xF0]:
    packet = bytearray(frame())
    packet[46] = tcp_size
    check(bytes(packet))

rng = random.Random(0x584450)
for _ in range(10000):
    if rng.randrange(2):
        packet = bytearray(frame(port=rng.choice([80, 3000, 65535]),
                                 vlan_tags=rng.choice([(), (0x8100,), (0x88A8, 0x8100)]),
                                 ihl=rng.choice([20, 24, 60]), tcp_header=rng.choice([20, 24, 60]),
                                 payload=rng.randbytes(rng.randrange(100))))
        for _ in range(rng.randrange(5)):
            packet[rng.randrange(len(packet))] = rng.randrange(256)
        packet = bytes(packet[:rng.randrange(len(packet) + 1)])
    else:
        packet = rng.randbytes(rng.randrange(300))
    check(packet, rng.choice([0, 80, 3000, 65535]), rng.choice([0, 63, 64]), rng.randrange(2))

print(f"PASS: {checks} offline packet/oracle checks (same generated Nelua classifier as BPF)")
