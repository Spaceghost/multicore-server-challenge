# Nelua XDP steering experiment

Typed Nelua packet classification compiled through C to a real eBPF ELF object.
The current object selects unfragmented IPv4/TCP traffic for an explicitly chosen
destination port and redirects it to an AF_XDP socket for the receiving queue.
Unselected/unsupported packets and absent socket-map entries return XDP_PASS.

**This is an unscored experiment outside the multicore challenge submission.**
The normal submission remains under `submissions/nelua-epoll-spaceghost`.
No script here loads/attaches BPF, creates packet sockets, changes NIC settings,
or modifies host networking. The implementation is a steering primitive; it does
not implement an AF_XDP application, TCP, HTTP, TLS, JWT, or PostgreSQL execution.

## What “closest to the NIC” means

| Mechanism | Where code executes | What it supplies | Remaining work |
| --- | --- | --- | --- |
| Ordinary epoll/io_uring socket I/O | Application on host CPU, Linux TCP stack beneath it | Ready TCP byte streams and ordinary HTTP integration | SQL scheduling, application work, serialization |
| Generic XDP / SKB mode | Host CPU, after an skb exists | Compatible fallback packet filter/redirect hook | Normal stack or a packet consumer |
| Native XDP / driver mode | Host CPU in the NIC driver's receive path, before normal skb allocation | Early packet classification/redirect/drop | Normal stack or a packet consumer |
| XDP hardware offload | A supported NIC's programmable hardware | A hardware-supported subset of XDP operations | Device/driver-specific support; host application still exists |
| AF_XDP | Host userspace with UMEM/rings, fed by an XDP program | Raw frames; zero-copy only where supported and successfully selected | TCP stack, retransmits/timers/congestion control, HTTP/TLS, and application |

eBPF is the verified program mechanism; XDP is one networking hook. AF_XDP is
packet I/O, and native XDP does **not** mean executing on the NIC. A normal
virtual NIC cannot be assumed to offer hardware offload or zero-copy. This
experiment targets software XDP-to-AF_XDP steering and makes no hardware-offload
compatibility claim. The Clang `-mcpu=v3` setting selects a BPF ISA level, not a
new runtime or a NIC execution mode.

XDP sees individual ingress frames, before TCP stream reassembly. A request
header, JSON body, or JWT can cross segments or arrive out of order; TLS payload
is encrypted. Redirecting TCP packets to AF_XDP bypasses the ordinary TCP socket
delivery path. An epoll HTTP server cannot simply receive those frames as its
existing connections: a correct packet consumer must own the selected TCP flow.
PostgreSQL's protocol, SQL executor, MVCC, WAL, and data permissions remain host
work. Moving a port classifier earlier does not make those costs disappear.

For this challenge, the leaders' large gain is sharing work among simultaneous
database requests within one batch. Early NIC processing can help packet/CPU
cost, but should be measured against that actual bottleneck rather than assumed
faster for the complete application.

## Build and verify without privileges

Uses [Spaceghost's Nelua fork](https://github.com/Spaceghost/nelua-lang) pinned to
`3c29419776dfdca194fa7e9c572498264fe5c654`. Its Lua compiler runs only at build
time. The packet code uses scalar/stack values with no VM, GC, allocator,
runtime initialization, or panic path.

```sh
cd experiments/nelua-xdp
# GCC/cc + Python: always builds/tests the shared native classifier.
bash build.sh
# Clang with the BPF backend also emits the actual ELF; zero disables steering.
NC_PORT=3000 CLANG=clang-18 bash tests/run.sh
```

Set `NELUA_ROOT=/path/to/clean/fork` to reuse an existing checkout. The build
rejects a different or modified compiler revision. `NC_PORT` defaults to zero:
the BPF entry returns PASS for every packet until built for a selected port.
`NC_PORT=1..65535` enables classification for that port, and redirection still
needs a live XSK map entry. Omitting Clang runs the native tests and reports that
the ELF was not built. GCC/Clang, make, binutils, git, and Python 3 are sufficient;
the BPF compilation uses small freestanding headers, not a kernel source tree.

The generated `build/nelua_xdp.o` has an `xdp` entry, a modern BTF `.maps`
XSKMAP named `nc_xsks`, and a license section. Its map supports RX queues 0–63;
the key is `ctx->rx_queue_index`. A future loader must create/bind the AF_XDP
socket to the same device and RX queue, supply UMEM/rings, and populate that key.
`bpf_redirect_map(..., XDP_PASS)` makes a missing entry pass to the normal stack.
This fallback does not promise recovery from a mismatched queue/device, ring
exhaustion, or a broken consumer: those can drop packets after map lookup.

`tools/audit.py` checks the actual ELF machine type, required BTF/map/program
sections, unresolved symbols, and helper-call IDs. **Compilation and ELF
inspection do not establish kernel-verifier acceptance.** No privileged verifier
load, NIC attachment, AF_XDP zero-copy check, or throughput measurement was
performed here.

## Parser and test scope

`src/steer.nelua` contains the actual parser. `src/entry.c` adds the XDP section,
UAPI context/map declarations, and a single helper call. The native test wrapper
uses the same generated parser and simulates only the final map-present decision.

Supported: Ethernet, up to two in-frame 802.1Q/802.1ad VLAN tags, IPv4 options,
TCP options, and selected destination-port classification. Explicit bounds checks
precede packet reads, and IPv4 total length/TCP header length are validated.
IPv6, ARP, non-TCP, IP fragments, deeper VLAN stacks, and truncated/unsupported
frames pass through. This parser does not validate IP/TCP checksums, maintain
connection state, or support XDP multi-buffer packets. Partial flow steering and
fragment fallback are additional reasons this is not a complete TCP datapath.

The native suite runs 17,605 differential checks against an independent Python
parser, including every truncation of option/VLAN-bearing test frames, missing
map entries, out-of-range queues, fragmentation, corrupt lengths, random bytes,
and mutated valid packets. The optional test runner also executes ASan/UBSan
against exact-size truncated/random buffers.

## Challenge eligibility

The published service unit grants `CAP_NET_BIND_SERVICE`, and the rules forbid
extra host/kernel tuning. Loading and attaching an XDP program or provisioning
an AF_XDP datapath needs network/BPF privileges and setup beyond that contract.
`install.sh` running as root does not authorize persistent privileged networking
changes. This path requires explicit organizer allowance or a separately labeled
benchmark on hardware under the user's control. It must not silently replace the
normal submission or report packet-only results as the application's score.

There is no rule exception that permits skipping PostgreSQL reads, replaying
cached API responses, weakening JWT/bcrypt verification, or acknowledging writes
before commit. Those requirements apply equally to an accelerated datapath.

## Primary references

- [Linux AF_XDP overview, UMEM, rings, queue matching, and zero-copy flags](https://docs.kernel.org/networking/af_xdp.html)
- [Linux XSKMAP documentation](https://docs.kernel.org/bpf/map_xskmap.html)
- [Linux eBPF verifier](https://docs.kernel.org/bpf/verifier.html)
- [Linux NFP driver and programmable SmartNIC firmware](https://docs.kernel.org/networking/device_drivers/ethernet/netronome/nfp.html)
- [Linux BPF syscall and token/capability model](https://docs.kernel.org/userspace-api/ebpf/syscall.html)
- [Kernel UAPI: helper 51 and redirect-map fallback flags](https://github.com/torvalds/linux/blob/master/include/uapi/linux/bpf.h)
- [iproute2 XDP driver/generic/offload mode documentation](https://git.kernel.org/pub/scm/network/iproute2/iproute2.git/tree/man/man8/ip-link.8.in)
- [Linux socket-lookup BPF hook: listening/unconnected sockets, not established TCP stream processing](https://docs.kernel.org/bpf/prog_sk_lookup.html)
- [Challenge service unit](../../box/challenge.service)
- [Challenge rules](../../README.md#rules)
