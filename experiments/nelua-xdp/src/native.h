#ifndef NELUA_XDP_NATIVE_H
#define NELUA_XDP_NATIVE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Only packet-range primitives cross this boundary; parsing stays in Nelua. */
static __attribute__((always_inline)) inline bool
nc_has(const unsigned char *data, const unsigned char *data_end, size_t amount)
{
    return data + amount <= data_end;
}

static __attribute__((always_inline)) inline unsigned char *
nc_advance(unsigned char *data, size_t amount)
{
    return data + amount;
}

/* Same UAPI layout as struct xdp_md in include/uapi/linux/bpf.h. */
struct nc_xdp_md {
    uint32_t data;
    uint32_t data_end;
    uint32_t data_meta;
    uint32_t ingress_ifindex;
    uint32_t rx_queue_index;
    uint32_t egress_ifindex;
};

#define NC_XDP_PASS 2
#define NC_XDP_REDIRECT 4
#define NC_BPF_MAP_TYPE_XSKMAP 17
#define NC_XSK_QUEUES 64

#endif
