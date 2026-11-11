/* Проверка PTFS и связки «файл -> ВМ» на ПК: test_ptfs образ_дискеты_B.img */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ptfs.h"
#include "../vm/vm.h"

static uint8_t *media;
static long media_len;
static int fails;

void media_read(uint32_t lba, uint8_t *dst) {
    if ((long)lba * 512 + 512 > media_len) { memset(dst, 0, 512); return; }
    memcpy(dst, media + (long)lba * 512, 512);
}

static void check(const char *name, long got, long exp) {
    if (got != exp) { fails++; printf("FAIL %s got %ld exp %ld\n", name, got, exp); }
}

static char out[256];
static int outn;
static int sys(vm_t *vm, uint8_t n, void *u) {
    (void)u;
    int32_t v;
    int r;
    if (n != 1) return VM_ERR_SYS;
    if ((r = vm_pop(vm, &v)) != 0) return r;
    if (outn < (int)sizeof out - 1) out[outn++] = (char)v;
    return 0;
}

static int run_file(const char *name) {
    static uint8_t buf[2048];
    static vm_t vm;
    ptfs_entry e;
    outn = 0; out[0] = 0;
    if (ptfs_find(name, &e) != PTFS_OK) return -100;
    int r = ptfs_read(&e, buf, sizeof buf);
    if (r != PTFS_OK) return r;
    static uint8_t mem[2048];
    r = vm_load(&vm, buf, e.size, mem, sizeof mem);
    if (r != 0) return r;
    vm.sys = sys;
    r = vm_run(&vm, 1000000);
    out[outn] = 0;
    return r;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open"); return 2; }
    media = malloc(4 << 20);
    media_len = (long)fread(media, 1, 4 << 20, f);
    fclose(f);

    check("mount", ptfs_mount(), PTFS_OK);
    check("count", ptfs_count(), 3);

    ptfs_entry e;
    check("get0", ptfs_get(0, &e), PTFS_OK);
    check("name0", strcmp(e.name, "hello.ptb"), 0);
    check("type0", e.type, PTFS_T_BYTECODE);
    check("find txt", ptfs_find("readme.txt", &e), PTFS_OK);
    check("type txt", e.type, PTFS_T_TEXT);
    check("find none", ptfs_find("nosuch", &e), PTFS_ERR_NOFILE);
    check("get oob", ptfs_get(3, &e), PTFS_ERR_NOFILE);

    check("run hello", run_file("hello.ptb"), VM_HALT);
    check("hello out", strcmp(out, "Hello from PT bytecode\n3628800\n"), 0);
    check("run fib", run_file("fib.ptb"), VM_HALT);
    check("fib out", strcmp(out, "0 1 1 2 3 5 8 13 21 34 \n"), 0);

    /* маленький буфер */
    static uint8_t tiny[100];
    ptfs_find("hello.ptb", &e);
    check("size err", ptfs_read(&e, tiny, sizeof tiny), PTFS_ERR_SIZE);

    /* порча данных файла: CRC должен поймать */
    ptfs_find("hello.ptb", &e);
    media[(1 + e.start) * 512 + 20] ^= 0x01;     /* +1 сектор заголовка носителя */
    check("crc err", run_file("hello.ptb"), PTFS_ERR_CRC);
    media[(1 + e.start) * 512 + 20] ^= 0x01;
    check("crc fixed", run_file("hello.ptb"), VM_HALT);

    /* порча заголовка носителя */
    media[0x10] ^= 0xFF;
    check("hdr crc", ptfs_mount(), PTFS_ERR_HDR_CRC);
    media[0x10] ^= 0xFF;
    media[0] = 'X';
    check("bad magic", ptfs_mount(), PTFS_ERR_MEDIA);
    media[0] = 'P';
    check("remount", ptfs_mount(), PTFS_OK);

    if (fails == 0) puts("PTFS TESTS PASS");
    else printf("PTFS TESTS FAIL: %d\n", fails);
    return fails != 0;
}