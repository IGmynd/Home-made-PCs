#include <stdint.h>

#define UART (*(volatile uint8_t *)0x10000000)
#define LSR  (*(volatile uint8_t *)0x10000005)
#define EXIT (*(volatile uint32_t *)0x100000)
#define MTIME_LO (*(volatile uint32_t *)0x0200BFF8)
#define CMP_LO (*(volatile uint32_t *)0x02004000)
#define CMP_HI (*(volatile uint32_t *)0x02004004)

#define csr_read(r) ({ uint32_t v; asm volatile("csrr %0, " #r : "=r"(v)); v; })
#define csr_write(r, v) asm volatile("csrw " #r ", %0" ::"r"(v))
#define csr_set(r, v) asm volatile("csrs " #r ", %0" ::"r"(v))
#define csr_clear(r, v) asm volatile("csrc " #r ", %0" ::"r"(v))

extern void trap_entry(void);
static volatile uint32_t last_cause, traps, irqs;
static int fails;

static void putc_(char c) { while (!(LSR & 0x20)) {} UART = c; }
static void puts_(const char *s) { while (*s) putc_(*s++); }
static void puthex(uint32_t v) {
    for (int i = 28; i >= 0; i -= 4) putc_("0123456789abcdef"[(v >> i) & 15]);
}

static void check(const char *name, uint32_t got, uint32_t exp) {
    if (got != exp) {
        fails++;
        puts_("FAIL "); puts_(name);
        puts_(" got "); puthex(got);
        puts_(" exp "); puthex(exp);
        puts_("\n");
    }
}

void trap_handler(void) {
    uint32_t c = csr_read(mcause);
    last_cause = c;
    if (c & 0x80000000u) {
        irqs++;
        CMP_HI = 0xFFFFFFFFu;                  /* выключить таймер */
    } else {
        traps++;
        csr_write(mepc, csr_read(mepc) + 4);
    }
}

static uint32_t twice(uint32_t x) { return x + x; }
static volatile uint8_t buf[8] __attribute__((aligned(4)));

void main(void) {
    csr_write(mtvec, (uint32_t)trap_entry);
    puts_("selftest start\n");

    volatile uint32_t a = 0x12345678, b = 0x0F0F0F0F, s = 4;
    volatile int32_t n = -16;
    check("add",  a + b, 0x21436587);
    check("sub",  a - b, 0x03254769);
    check("and",  a & b, 0x02040608);
    check("or",   a | b, 0x1F3F5F7F);
    check("xor",  a ^ b, 0x1D3B5977);
    check("sll",  a << s, 0x23456780);
    check("srl",  a >> s, 0x01234567);
    check("sra",  (uint32_t)(n >> 2), 0xFFFFFFFC);
    check("srl2", (uint32_t)n >> 4, 0x0FFFFFFF);
    check("slt",  (n < (int32_t)a) ? 1 : 0, 1);
    check("sltu", ((uint32_t)n < a) ? 1 : 0, 0);

    volatile uint32_t sum = 0;
    for (uint32_t i = 1; i <= 10; i++) sum += i;
    check("loop", sum, 55);

    buf[0] = 0x11; buf[1] = 0x22; buf[2] = 0x33; buf[3] = 0x44;
    check("lw",  *(volatile uint32_t *)buf, 0x44332211);
    check("lhu", *(volatile uint16_t *)&buf[2], 0x4433);
    buf[4] = 0x80;
    check("lb",  (uint32_t)(int32_t)*(volatile int8_t *)&buf[4], 0xFFFFFF80);
    check("lbu", buf[4], 0x80);
    *(volatile uint16_t *)&buf[6] = 0xBEEF;
    check("sh lo", buf[6], 0xEF);
    check("sh hi", buf[7], 0xBE);

    uint32_t (*volatile fp)(uint32_t) = twice;
    check("jalr", fp(21), 42);

    csr_write(mscratch, 0xdeadbeefu);
    check("csrw", csr_read(mscratch), 0xdeadbeef);
    csr_set(mscratch, 0x0000ffffu);
    check("csrs", csr_read(mscratch), 0xdeadffff);
    csr_clear(mscratch, 0x0000ff00u);
    check("csrc", csr_read(mscratch), 0xdead00ff);

    asm volatile("ecall");
    check("ecall n", traps, 1);
    check("ecall c", last_cause, 11);
    asm volatile(".word 0xffffffff");
    check("illegal n", traps, 2);
    check("illegal c", last_cause, 2);

    CMP_HI = 0xFFFFFFFFu;
    CMP_LO = MTIME_LO + 20;
    CMP_HI = 0;
    csr_set(mie, 0x80);
    csr_set(mstatus, 0x8);
    uint32_t guard = 0;
    while (!irqs && guard < 100000) guard++;
    csr_clear(mstatus, 0x8);
    check("timer n", irqs, 1);
    check("timer c", last_cause, 0x80000007);

    if (fails == 0) puts_("SELFTEST PASS\n");
    else { puts_("SELFTEST FAIL\n"); }
    EXIT = 0x5555;
    for (;;) {}
}