/* Проверки ВМ: арифметика, ошибки, лимиты. Печатает "VM TESTS PASS" при успехе. */
#include <stdio.h>
#include <string.h>
#include "vm.h"

static int fails;

static void check(const char *name, long got, long exp) {
    if (got != exp) {
        fails++;
        printf("FAIL %s got %ld exp %ld\n", name, got, exp);
    }
}

/* Собирает образ из кода и запускает. Результат vm_run возвращается, ВМ остаётся в *vm. */
static int run(vm_t *vm, const uint8_t *code, uint32_t n, uint32_t steps) {
    static uint8_t img[512], mem[256];
    uint32_t ds = 0;
    memcpy(img, "PTBC", 4);
    img[4] = 1; img[5] = 0; img[6] = 0; img[7] = 0;
    img[8] = (uint8_t)n; img[9] = img[10] = img[11] = 0;
    memcpy(img + 12, &ds, 4);
    memcpy(img + 16, code, n);
    int r = vm_load(vm, img, 16 + n, mem, sizeof mem);
    if (r != 0) return r;
    return vm_run(vm, steps);
}

#define CODE(...) static const uint8_t c[] = { __VA_ARGS__ }
#define RUN(steps) run(&vm, c, sizeof c, steps)
#define P8(x) 0x01, (uint8_t)(x)
#define P32(x) 0x02, (uint8_t)(x), (uint8_t)((x) >> 8), (uint8_t)((x) >> 16), (uint8_t)((x) >> 24)

static void t_arith(void) {
    vm_t vm;
    { CODE(P8(7), P8(3), 0x10, 0x00); check("add", RUN(0), VM_HALT); check("add v", vm.ds[0], 10); }
    { CODE(P8(7), P8(3), 0x11, 0x00); RUN(0); check("sub", vm.ds[0], 4); }
    { CODE(P8(-7), P8(3), 0x12, 0x00); RUN(0); check("mul", vm.ds[0], -21); }
    { CODE(P8(-7), P8(2), 0x13, 0x00); RUN(0); check("div", vm.ds[0], -3); }
    { CODE(P8(-7), P8(2), 0x14, 0x00); RUN(0); check("mod", vm.ds[0], -1); }
    { CODE(P8(12), P8(10), 0x15, 0x00); RUN(0); check("and", vm.ds[0], 8); }
    { CODE(P8(12), P8(10), 0x16, 0x00); RUN(0); check("or", vm.ds[0], 14); }
    { CODE(P8(12), P8(10), 0x17, 0x00); RUN(0); check("xor", vm.ds[0], 6); }
    { CODE(P8(1), P8(4), 0x18, 0x00); RUN(0); check("shl", vm.ds[0], 16); }
    { CODE(P8(-16), P8(28), 0x19, 0x00); RUN(0); check("shr", vm.ds[0], 15); }
    { CODE(P8(-16), P8(2), 0x1A, 0x00); RUN(0); check("sar", vm.ds[0], -4); }
    { CODE(P8(5), 0x1B, 0x00); RUN(0); check("neg", vm.ds[0], -5); }
    { CODE(P8(0), 0x1C, 0x00); RUN(0); check("not", vm.ds[0], -1); }
    { CODE(P8(3), P8(3), 0x20, 0x00); RUN(0); check("eq", vm.ds[0], 1); }
    { CODE(P8(3), P8(4), 0x22, 0x00); RUN(0); check("lt", vm.ds[0], 1); }
    { CODE(P8(-1), P8(1), 0x22, 0x00); RUN(0); check("lt signed", vm.ds[0], 1); }
    { CODE(P8(3), P8(4), 0x25, 0x00); RUN(0); check("ge", vm.ds[0], 0); }
    { CODE(P32(0x80000000u), P8(-1), 0x13, 0x00); RUN(0); check("div ovf", (uint32_t)vm.ds[0], 0x80000000u); }
    { CODE(P32(0x80000000u), P8(-1), 0x14, 0x00); RUN(0); check("mod ovf", vm.ds[0], 0); }
    { CODE(P32(0x7FFFFFFFu), P8(1), 0x10, 0x00); RUN(0); check("add wrap", (uint32_t)vm.ds[0], 0x80000000u); }
}

static void t_stack(void) {
    vm_t vm;
    { CODE(P8(1), P8(2), 0x05, 0x00); RUN(0); check("swap0", vm.ds[0], 2); check("swap1", vm.ds[1], 1); }
    { CODE(P8(1), P8(2), 0x06, 0x00); RUN(0); check("over n", vm.sp, 3); check("over", vm.ds[2], 1); }
    { CODE(P8(1), 0x03, 0x04, 0x00); RUN(0); check("dup/drop n", vm.sp, 1); }
}

static void t_errors(void) {
    vm_t vm;
    { CODE(0x10); check("underflow", RUN(0), VM_ERR_DS_UNDER); }
    { CODE(P8(1), P8(0), 0x13, 0x00); check("div0", RUN(0), VM_ERR_DIV0); }
    { CODE(P8(1), P8(0), 0x14, 0x00); check("mod0", RUN(0), VM_ERR_DIV0); }
    { CODE(0xEE); check("badop", RUN(0), VM_ERR_BADOP); }
    { CODE(0x02, 1, 2); check("truncated", RUN(0), VM_ERR_BADOP); }
    { CODE(P8(1)); check("falls off end", RUN(0), VM_ERR_JUMP); }
    { CODE(0x40, 99, 0, 0, 0); check("bad jump", RUN(0), VM_ERR_JUMP); }
    { CODE(P8(1), 0x40, 0, 0, 0, 0); check("stack over", RUN(0), VM_ERR_DS_OVER); }
    { CODE(0x43, 0, 0, 0, 0); check("call over", RUN(0), VM_ERR_RS_OVER); }
    { CODE(0x44); check("ret under", RUN(0), VM_ERR_RS_UNDER); }
    { CODE(0x40, 0, 0, 0, 0); check("steps", RUN(100), VM_ERR_STEPS); }
    { CODE(P8(0), P32(0x7FFFFFF0u), 0x30, 0x00); check("mem oob", RUN(0), VM_ERR_MEM); }
    { CODE(P32(0xFFFFFFFFu), 0x32, 0x00); check("mem neg", RUN(0), VM_ERR_MEM); }
    { CODE(0x50, 1); check("no sys", RUN(0), VM_ERR_SYS); }
}

static void t_mem(void) {
    vm_t vm;
    { CODE(P32(0x11223344u), P8(8), 0x31, P8(8), 0x30, P8(9), 0x32, 0x00);
      check("mem run", RUN(0), VM_HALT);
      check("ld32", vm.ds[0], 0x11223344);
      check("ld8 byte1", vm.ds[1], 0x33); }
    { CODE(P8(-86), P8(5), 0x33, P8(5), 0x32, 0x00); RUN(0); check("st8/ld8", vm.ds[0], 0xAA); }
}

static void t_frames(void) {
    vm_t vm;
    /* frame 2; push 7; stl 0; push 9; stl 1; ldl 0; ldl 1; add; leave; halt */
    { CODE(0x60, 2, P8(7), 0x63, 0, P8(9), 0x63, 1, 0x62, 0, 0x62, 1, 0x10, 0x61, 0x00);
      check("frame run", RUN(0), VM_HALT); check("frame val", vm.ds[0], 16); check("frame fp", vm.fp, vm.fp_top); }
    { CODE(0x60, 1, 0x62, 0, 0x61, 0x00); RUN(0); check("frame zeroed", vm.ds[0], 0); }
    { CODE(0x61); check("leave no frame", RUN(0), VM_ERR_FRAME); }
    { CODE(0x62, 0); check("ldl no frame", RUN(0), VM_ERR_FRAME); }
    { CODE(0x60, 1, 0x62, 1); check("ldl range", RUN(0), VM_ERR_FRAME); }
    { CODE(0x60, 1, P8(5), 0x63, 3); check("stl range", RUN(0), VM_ERR_FRAME); }
    { CODE(0x60, 100); check("frame too big", RUN(0), VM_ERR_FRAME); }
    { CODE(0x60, 20, 0x40, 0, 0, 0, 0); check("frame overflow", RUN(0), VM_ERR_FRAME); }
    /* программа портит заголовок своего кадра: ldl обязан отказать, а не читать за пределами памяти */
    { CODE(0x60, 1, P32(1000000), P32(248), 0x31, 0x62, 200); check("corrupt n ldl", RUN(0), VM_ERR_FRAME); }
    { CODE(0x60, 1, P32(1000000), P32(248), 0x31, P8(5), 0x63, 200); check("corrupt n stl", RUN(0), VM_ERR_FRAME); }
    /* вложенные кадры и восстановление: frame 1; push 5; stl 0; frame 1; push 6; stl 0; leave; ldl 0; leave; halt */
    { CODE(0x60, 1, P8(5), 0x63, 0, 0x60, 1, P8(6), 0x63, 0, 0x61, 0x62, 0, 0x61, 0x00);
      check("nested", RUN(0), VM_HALT); check("nested val", vm.ds[0], 5); }
}

static void t_heap(void) {
    vm_t vm;
    /* alloc 8 -> адрес, пишем и читаем слово */
    { CODE(P8(8), 0x52, 0x03, P32(777), 0x05, 0x31, 0x30, 0x00);   /* alloc; dup; push 777; swap; st32; ld32 */
      check("alloc run", RUN(0), VM_HALT); check("alloc val", vm.ds[0], 777); }
    { CODE(P8(5), 0x52, P8(1), 0x52, 0x00); RUN(0);                /* 5 байт округляются до 8 */
      check("alloc first", vm.ds[0], 0); check("alloc second", vm.ds[1], 8); }
    { CODE(P8(-1), 0x52, 0x00); check("alloc negative", RUN(0), VM_ERR_MEM); }
    { CODE(P32(100000), 0x52, 0x00); check("alloc too big", RUN(0), VM_ERR_MEM); }
    { CODE(0x51, 7); check("trap", RUN(0), VM_ERR_TRAP); check("trap code", vm.trap_code, 7); }
    { CODE(0x51); check("trap truncated", RUN(0), VM_ERR_BADOP); }
    /* куча и кадры не пересекаются: после большой кучи кадр не помещается */
    { CODE(P8(100), 0x52, 0x04, 0x60, 60, 0x00); check("heap blocks frame", RUN(0), VM_ERR_FRAME); }
    /* после кадра куча не может залезть на него */
    { CODE(0x60, 40, P8(100), 0x52, 0x00); check("frame blocks heap", RUN(0), VM_ERR_MEM); }
}
static void t_load(void) {
    vm_t vm;
    static uint8_t mem[16];
    uint8_t bad[16] = {'X', 'T', 'B', 'C', 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    check("bad magic", vm_load(&vm, bad, 16, mem, sizeof mem), VM_ERR_IMAGE);
    bad[0] = 'P'; bad[4] = 2;
    check("bad version", vm_load(&vm, bad, 16, mem, sizeof mem), VM_ERR_IMAGE);
    bad[4] = 1; bad[8] = 50;
    check("code too long", vm_load(&vm, bad, 16, mem, sizeof mem), VM_ERR_IMAGE);
    check("short image", vm_load(&vm, bad, 8, mem, sizeof mem), VM_ERR_IMAGE);
}

int main(void) {
    t_arith();
    t_stack();
    t_errors();
    t_mem();
    t_frames();
    t_heap();
    t_load();
    if (fails == 0) puts("VM TESTS PASS");
    else printf("VM TESTS FAIL: %d\n", fails);
    return fails != 0;
}