#include "ptfs.h"
#include "../boot/crc32.h"

#define SECTOR 512

static uint8_t dir[SECTOR];
static uint32_t base;        /* LBA начала области образа */
static uint32_t span;        /* размер области образа в секторах */
static int mounted, count;

static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

int ptfs_mount(void) {
    uint8_t h[SECTOR];
    mounted = 0;
    media_read(0, h);
    if (rd32(h) != 0x444d5450u) return PTFS_ERR_MEDIA;                 /* "PTMD" */
    if (crc32_update(0, h, 0x1FC) != rd32(h + 0x1FC)) return PTFS_ERR_HDR_CRC;
    base = rd32(h + 0x20);
    span = rd32(h + 0x24);
    if (span == 0) return PTFS_ERR_EMPTY;
    media_read(base, dir);
    if (rd32(dir) != 0x53465450u || dir[4] != 1 || dir[5] != 0) return PTFS_ERR_MAGIC;   /* "PTFS" v1 */
    count = dir[6] | (dir[7] << 8);
    if (count > PTFS_MAX_FILES) return PTFS_ERR_COUNT;
    mounted = 1;
    return PTFS_OK;
}

int ptfs_count(void) { return mounted ? count : 0; }

int ptfs_get(int i, ptfs_entry *e) {
    if (!mounted || i < 0 || i >= count) return PTFS_ERR_NOFILE;
    const uint8_t *p = dir + 32 + 32 * i;
    for (int k = 0; k < 16; k++) e->name[k] = (char)p[k];
    e->name[16] = 0;
    e->start = rd32(p + 16);
    e->size  = rd32(p + 20);
    e->crc   = rd32(p + 24);
    e->type  = p[28];
    return PTFS_OK;
}

static int same(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

int ptfs_find(const char *name, ptfs_entry *e) {
    for (int i = 0; ptfs_get(i, e) == PTFS_OK; i++)
        if (same(e->name, name)) return PTFS_OK;
    return PTFS_ERR_NOFILE;
}

int ptfs_read(const ptfs_entry *e, uint8_t *dst, uint32_t cap) {
    if (!mounted) return PTFS_ERR_MEDIA;
    if (e->size > cap) return PTFS_ERR_SIZE;
    uint32_t sects = (e->size + SECTOR - 1) / SECTOR;
    if (sects * SECTOR > cap) return PTFS_ERR_SIZE;
    if (e->start < 1 || e->start > span || sects > span - e->start) return PTFS_ERR_SIZE;
    for (uint32_t i = 0; i < sects; i++) media_read(base + e->start + i, dst + i * SECTOR);
    if (crc32_update(0, dst, e->size) != e->crc) return PTFS_ERR_CRC;
    return PTFS_OK;
}