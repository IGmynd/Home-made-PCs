/* Запуск программы PTBC на ПК: host файл.ptb
   Системные вызовы: 1 = вывод байта, 2 = ввод байта без ожидания, 3 = ввод строки. */
#include <stdio.h>
#include <stdlib.h>
#include "vmio.h"

static int host_sys(vm_t *vm, uint8_t n, void *user) {
    (void)user;
    int32_t v;
    int r;
    switch (n) {
    case VM_SYS_PUTC:
        if ((r = vm_pop(vm, &v)) != 0) return r;
        putchar((int)(v & 0xFF));
        return 0;
    case VM_SYS_GETC:
        return vm_push(vm, getchar());
    case VM_SYS_READLINE: {
        static uint8_t line[4096];
        size_t len = 0;
        int c;
        while ((c = getchar()) != EOF && c != '\n')
            if (len < sizeof line) line[len++] = (uint8_t)c;
        if (len > 0 && line[len - 1] == '\r') len--;
        return vm_push_utf8(vm, line, (uint32_t)len);
    }
    default:
        return VM_ERR_SYS;
    }
}

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: host file.ptb\n"); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open"); return 2; }
    static uint8_t img[1 << 20], mem[1 << 16];
    size_t len = fread(img, 1, sizeof img, f);
    fclose(f);

    static vm_t vm;
    int r = vm_load(&vm, img, (uint32_t)len, mem, sizeof mem);
    if (r != 0) { fprintf(stderr, "load error %d\n", r); return 1; }
    vm.sys = host_sys;
    r = vm_run(&vm, 10000000);
    if (r != VM_HALT) { fprintf(stderr, "vm error %d at pc=%u\n", r, vm.pc); return 1; }
    return 0;
}