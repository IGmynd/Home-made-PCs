/* Проверки vm_push_utf8: нормальные и испорченные последовательности. Печатает "VMIO TESTS PASS". */
#include <stdio.h>
#include <string.h>
#include "vmio.h"

static int fails;

static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Подготовить ВМ с пустой программой и памятью mem_len байт. */
static void init(vm_t *vm, uint8_t *mem, uint32_t mem_len) {
    static const uint8_t img[17] = {'P', 'T', 'B', 'C', 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0};
    vm_load(vm, img, sizeof img, mem, mem_len);
}

/* Преобразует байты и сверяет с ожидаемыми кодами. */
static void check(const char *name, const uint8_t *s, uint32_t n, const uint32_t *exp, uint32_t cnt) {
    static uint8_t mem[1024];
    vm_t vm;
    init(&vm, mem, sizeof mem);
    int r = vm_push_utf8(&vm, s, n);
    if (r != 0) { fails++; printf("FAIL %s: код ошибки %d\n", name, r); return; }
    int32_t addr;
    vm_pop(&vm, &addr);
    uint32_t len = rd32(mem + addr);
    if (len != cnt) { fails++; printf("FAIL %s: длина %u, ждали %u\n", name, len, cnt); return; }
    for (uint32_t i = 0; i < cnt; i++) {
        uint32_t got = rd32(mem + addr + 4 + 4 * i);
        if (got != exp[i]) { fails++; printf("FAIL %s: символ %u это %x, ждали %x\n", name, i, got, exp[i]); return; }
    }
}

#define T(name, bytes, ...) do { \
    static const uint8_t b[] = bytes; static const uint32_t e[] = { __VA_ARGS__ }; \
    check(name, b, sizeof b - 1, e, sizeof e / sizeof e[0]); } while (0)

int main(void) {
    { static const uint32_t none[1] = {0}; check("пусто", (const uint8_t *)"", 0, none, 0); }
    T("ascii", "abc", 97, 98, 99);
    T("2 байта", "\xD1\x8F", 0x44F);
    T("3 байта", "\xE2\x82\xAC", 0x20AC);
    T("4 байта", "\xF0\x9F\x98\x80", 0x1F600);
    T("смесь", "a\xD0\xBF\xE2\x82\xAC\xF0\x9F\x98\x80z", 97, 0x43F, 0x20AC, 0x1F600, 122);
    T("граница 7f", "\x7F", 0x7F);
    T("граница 2 байт", "\xC2\x80\xDF\xBF", 0x80, 0x7FF);
    T("граница 3 байт", "\xE0\xA0\x80\xEF\xBF\xBF", 0x800, 0xFFFF);
    T("граница 4 байт", "\xF0\x90\x80\x80\xF4\x8F\xBF\xBF", 0x10000, 0x10FFFF);

    T("чужой байт", "\xFF", 0xFFFD);
    T("чужие байты", "\xFF\xFE", 0xFFFD, 0xFFFD);
    T("посреди текста", "a\xFF" "b", 97, 0xFFFD, 98);
    T("оборванная 2", "\xD1", 0xFFFD);
    T("оборванная 3", "\xE2\x82", 0xFFFD, 0xFFFD);
    T("оборванная 4", "\xF0\x9F\x98", 0xFFFD, 0xFFFD, 0xFFFD);
    T("лишняя добавочная", "\x80", 0xFFFD);
    T("лишне длинная 2", "\xC0\x80", 0xFFFD, 0xFFFD);
    T("лишне длинная 3", "\xE0\x80\x80", 0xFFFD, 0xFFFD, 0xFFFD);
    T("лишне длинная 4", "\xF0\x80\x80\x80", 0xFFFD, 0xFFFD, 0xFFFD, 0xFFFD);
    T("суррогат", "\xED\xA0\x80", 0xFFFD, 0xFFFD, 0xFFFD);
    T("за пределом юникода", "\xF4\x90\x80\x80", 0xFFFD, 0xFFFD, 0xFFFD, 0xFFFD);
    T("байт F5", "\xF5\x80\x80\x80", 0xFFFD, 0xFFFD, 0xFFFD, 0xFFFD);
    T("после ошибки всё нормально", "\xD1\xD1\x8F", 0xFFFD, 0x44F);

    /* нехватка памяти: 16 байт памяти, строка из 10 букв не поместится */
    {
        static uint8_t tiny[16];
        vm_t vm;
        init(&vm, tiny, sizeof tiny);
        int r = vm_push_utf8(&vm, (const uint8_t *)"0123456789", 10);
        if (r != VM_ERR_MEM) { fails++; printf("FAIL нехватка памяти: %d\n", r); }
    }
    /* стек данных полон: после выделения push должен вернуть ошибку, а не писать мимо */
    {
        static uint8_t mem[256];
        vm_t vm;
        init(&vm, mem, sizeof mem);
        for (int i = 0; i < PTVM_DS_SIZE; i++) vm_push(&vm, i);
        int r = vm_push_utf8(&vm, (const uint8_t *)"a", 1);
        if (r != VM_ERR_DS_OVER) { fails++; printf("FAIL полный стек: %d\n", r); }
    }

    if (fails == 0) puts("VMIO TESTS PASS");
    else printf("VMIO TESTS FAIL: %d\n", fails);
    return fails != 0;
}