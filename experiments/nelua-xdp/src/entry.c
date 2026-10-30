/* Included after generated steer.c, so Clang can inline the typed Nelua parser. */
#include "native.h"

#ifndef NC_PORT
#define NC_PORT 0
#endif

#if NC_PORT < 0 || NC_PORT > 65535
#error NC_PORT must be in 0..65535; zero disables redirection
#endif

#define NC_SEC(name) __attribute__((section(name), used))

#ifdef NC_BPF

/* Modern BTF map definition understood by libbpf, without libbpf header imports. */
struct {
    int (*type)[NC_BPF_MAP_TYPE_XSKMAP];
    int (*max_entries)[NC_XSK_QUEUES];
    uint32_t *key;
    uint32_t *value;
} nc_xsks NC_SEC(".maps");

static long (*const nc_redirect_map)(void *, uint64_t, uint64_t) = (void *) 51;

NC_SEC("xdp") int nc_xdp_steer(struct nc_xdp_md *ctx)
{
    unsigned char *data = (void *) (unsigned long) ctx->data;
    unsigned char *end = (void *) (unsigned long) ctx->data_end;
    if (!nc_packet_selected(data, end, NC_PORT)) return NC_XDP_PASS;
    /* Low flag bits select PASS when the map lookup has no socket. */
    return (int) nc_redirect_map(&nc_xsks, ctx->rx_queue_index, NC_XDP_PASS);
}

char nc_license[] NC_SEC("license") = "MIT";

#else

/* Native simulation does not call bpf(), create sockets, or attach anything. */
int nc_offline_action(unsigned char *data, size_t length, uint16_t port,
                      uint32_t queue, int mapped)
{
    if (!nc_packet_selected(data, data + length, port)) return NC_XDP_PASS;
    return mapped && queue < NC_XSK_QUEUES ? NC_XDP_REDIRECT : NC_XDP_PASS;
}

#endif
