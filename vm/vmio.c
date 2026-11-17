#include "vmio.h"

#define REPLACEMENT 0xFFFDu
#define MAX_CHARS   16777216u        /* столько же, сколько в списках Слога */

static int is_cont(uint8_t b) { return (b & 0xC0u) == 0x80u; }

/* Читает один символ из s (доступно avail >= 1 байт). Возвращает, сколько байт съедено (>= 1). */
static uint32_t utf8_next(const uint8_t *s, uint32_t avail, uint32_t *cp) {
    uint8_t b = s[0];
    *cp = REPLACEMENT;
    if (b < 0x80) { *cp = b; return 1; }
    if (b >= 0xC2 && b <= 0xDF) {
        if (avail >= 2 && is_cont(s[1])) {
            *cp = ((uint32_t)(b & 0x1Fu) << 6) | (s[1] & 0x3Fu);
            return 2;
        }
        return 1;
    }
    if (b >= 0xE0 && b <= 0xEF) {
        if (avail >= 3 && is_cont(s[1]) && is_cont(s[2])) {
            if (b == 0xE0 && s[1] < 0xA0) return 1;          /* лишне длинная запись */
            if (b == 0xED && s[1] > 0x9F) return 1;          /* суррогаты не символы */
            *cp = ((uint32_t)(b & 0x0Fu) << 12) | ((uint32_t)(s[1] & 0x3Fu) << 6) | (s[2] & 0x3Fu);
            return 3;
        }
        return 1;
    }
    if (b >= 0xF0 && b <= 0xF4) {
        if (avail >= 4 && is_cont(s[1]) && is_cont(s[2]) && is_cont(s[3])) {
            if (b == 0xF0 && s[1] < 0x90) return 1;
            if (b == 0xF4 && s[1] > 0x8F) return 1;
            *cp = ((uint32_t)(b & 0x07u) << 18) | ((uint32_t)(s[1] & 0x3Fu) << 12)
                | ((uint32_t)(s[2] & 0x3Fu) << 6) | (s[3] & 0x3Fu);
            return 4;
        }
        return 1;
    }
    return 1;                                                /* 0x80-0xC1, 0xF5-0xFF */
}

static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

int vm_push_utf8(vm_t *vm, const uint8_t *s, uint32_t n) {
    uint32_t count = 0, cp;
    for (uint32_t i = 0; i < n; count++) i += utf8_next(s + i, n - i, &cp);
    if (count > MAX_CHARS) return VM_ERR_MEM;

    uint32_t base;
    int r = vm_alloc(vm, 4u * (count + 1u), &base);
    if (r != 0) return r;
    put32(vm->mem + base, count);
    uint32_t k = 0;
    for (uint32_t i = 0; i < n; k++) {
        i += utf8_next(s + i, n - i, &cp);
        put32(vm->mem + base + 4u * (k + 1u), cp);
    }
    return vm_push(vm, (int32_t)base);
}