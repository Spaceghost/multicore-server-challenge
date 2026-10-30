#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int nc_offline_action(unsigned char *, size_t, uint16_t, uint32_t, int);

static uint32_t state = 0x584450U;
static uint32_t random32(void)
{
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

int main(void)
{
    unsigned char valid[54] = {0};
    unsigned int i;
    volatile int actions = 0;
    valid[12] = 8;
    valid[14] = 0x45;
    valid[17] = 40;
    valid[23] = 6;
    valid[36] = 0x0b;
    valid[37] = 0xb8;
    valid[46] = 0x50;

    for (i = 0; i <= sizeof(valid); ++i) {
        unsigned char *packet = malloc(i ? i : 1);
        if (!packet) return 1;
        memcpy(packet, valid, i);
        actions += nc_offline_action(packet, i, 3000, 0, 1);
        free(packet);
    }
    for (i = 0; i < 20000; ++i) {
        size_t length = random32() % 2048;
        size_t j;
        unsigned char *packet = malloc(length ? length : 1);
        if (!packet) return 1;
        for (j = 0; j < length; ++j) packet[j] = (unsigned char) random32();
        if (length >= sizeof(valid) && (i & 1)) {
            memcpy(packet, valid, sizeof(valid));
            packet[14 + (random32() % 40)] = (unsigned char) random32();
        }
        actions += nc_offline_action(packet, length, 3000, random32() % 65, i & 1);
        free(packet);
    }
    printf("PASS: ASan/UBSan packet truncation and randomized buffers (%d actions)\n", actions);
    return 0;
}
