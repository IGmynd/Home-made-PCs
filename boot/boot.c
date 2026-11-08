#include <stdint.h>
#include "crc32.h"

#define UART (*(volatile uint8_t *)0x10000000)
#define SECTOR 512
#define MEDIA_BASE 0x80200000u /* пока "дискета" лежит в ОЗУ, QEMU кладёт её сюда */

static void puts_(const char *s) { while (*s) UART = *s++; }

static void puthex(uint32_t v) {
    for (int i = 28; i >= 0; i -= 4) UART = "0123456789abcdef"[(v >> i) & 15];
}

static uint32_t rd32(const uint8_t *p) {
    return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Единственное место, которое знает про устройство. Потом тут будет драйвер флоппи. */
static void blk_read(uint32_t lba, uint8_t *dst) {
    const uint8_t *src = (const uint8_t *)(MEDIA_BASE + lba * SECTOR);
    for (int i = 0; i < SECTOR; i++) dst[i] = src[i];
}

static void fail(const char *m) {
    puts_("BOOT FAIL: ");
    puts_(m);
    puts_("\n");
    for (;;) {}
}

void main(void) {
    uint8_t h[SECTOR];
    puts_("PT boot rom v0\n");

    blk_read(0, h);
    if (rd32(h) != 0x444d5450u) fail("magic");               /* "PTMD" */
    if (crc32_update(0, h, 0x1FC) != rd32(h + 0x1FC)) fail("header crc");
    puts_("header crc ok\n");
    if (h[6] != 1 || !(h[7] & 1)) fail("not a boot media");  /* класс 1 + флаг загрузочного */

    uint32_t lba = rd32(h + 0x20), n = rd32(h + 0x24);
    uint32_t load = rd32(h + 0x28), entry = rd32(h + 0x2C), icrc = rd32(h + 0x30);

    uint32_t crc = 0;
    for (uint32_t i = 0; i < n; i++) {
        uint8_t *dst = (uint8_t *)(load + i * SECTOR);
        blk_read(lba + i, dst);
        crc = crc32_update(crc, dst, SECTOR);
    }
    if (crc != icrc) fail("image crc");

    puts_("image crc ok, jump to 0x");
    puthex(entry);
    puts_("\n");
    ((void (*)(void))entry)();
}