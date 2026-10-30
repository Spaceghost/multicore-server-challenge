# Offline validation — 2026-10-30

| Component | Result |
| --- | --- |
| Nelua compiler | Spaceghost/nelua-lang `3c29419776dfdca194fa7e9c572498264fe5c654` |
| Native compiler | GCC 13.3.0, Linux x86-64 |
| eBPF compiler | Ubuntu Clang 18.1.3, BPF little-endian, ISA v3 |
| Native packet/oracle suite | 17,605 checks passed |
| Exact-size buffer sanitizer run | ASan/UBSan passed over valid truncations and 20,000 random/mutated buffers |
| Selected-port BPF object | Compiled for destination TCP port 3000 |
| XDP instructions | 92, occupying 736 bytes |
| Helper calls | Helper 51, `bpf_redirect_map`, once on the selected path |
| ELF size, including BTF/debug metadata | 11,760 bytes in this development build |
| BTF map | `nc_xsks`, XSKMAP, queue keys 0–63 |
| Out-of-line helper code | None; `.text` is empty, parser is inlined into the XDP entry |
| Undefined/runtime symbols | None |
| Whitespace, Python, shell syntax | Passed |

The object was inspected as ELF64/EM_BPF and contains `xdp`, `.maps`, `.BTF`, and
`license` sections. The selected-port program is real BPF machine code, not a
native-host object with an XDP label. The same Nelua parser is compiled into the
native differential test library.

No BPF syscall, kernel verifier load, program attachment, AF_XDP socket, NIC
configuration, userspace TCP stack, hardware offload, or throughput benchmark was
performed. ELF compilation and native sanitizer tests cannot establish verifier
acceptance or datapath performance on a target kernel/NIC. The build has no
loading/attachment step, and nothing changed host networking.

Clang and its runtime libraries were downloaded/extracted into scratch for this
test, without installing packages globally. Those toolchain files and generated
objects are excluded from the repository deliverable.

Reproduce on a Linux system with Clang's BPF backend:

```sh
NELUA_ROOT=/path/to/clean/nelua-fork NC_PORT=3000 CLANG=clang-18 bash tests/run.sh
```
