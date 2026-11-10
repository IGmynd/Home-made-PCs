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
    /* ----- расширение M: каждая команда отдельно, через asm ----- */
#define OP2(name, a, b) ({ uint32_t r_; asm volatile(name " %0, %1, %2" : "=r"(r_) : "r"(a), "r"(b)); r_; })
    volatile uint32_t m7 = 0xFFFFFFF9u, m3 = 3u, mneg1 = 0xFFFFFFFFu;
    volatile uint32_t mmin = 0x80000000u, mz = 0u, m5 = 5u, m7p = 7u, mneg2 = 0xFFFFFFFEu;
    check("mul",    OP2("mul",    m7, m3), 0xFFFFFFEB);
    check("mulh",   OP2("mulh",   m7, m3), 0xFFFFFFFF);
    check("mulhu",  OP2("mulhu",  m7, m3), 2);
    check("mulhsu", OP2("mulhsu", m7, m3), 0xFFFFFFFF);
    check("mulh2",  OP2("mulh",   mmin, mmin), 0x40000000);
    check("mul2",   OP2("mul",    mmin, mmin), 0);
    check("div",    OP2("div",    m7, m3), 0xFFFFFFFE);
    check("rem",    OP2("rem",    m7, m3), 0xFFFFFFFF);
    check("divu",   OP2("divu",   m7, m3), 0x55555553);
    check("remu",   OP2("remu",   m7, m3), 0);
    check("div/0",  OP2("div",    m5, mz), 0xFFFFFFFF);
    check("rem/0",  OP2("rem",    m5, mz), 5);
    check("divu/0", OP2("divu",   m7p, mz), 0xFFFFFFFF);
    check("remu/0", OP2("remu",   m7p, mz), 7);
    check("divovf", OP2("div",    mmin, mneg1), 0x80000000);
    check("removf", OP2("rem",    mmin, mneg1), 0);
    check("div7/-2", OP2("div",   m7p, mneg2), 0xFFFFFFFD);
    check("rem7/-2", OP2("rem",   m7p, mneg2), 1);

    /* ----- расширение C: конкретные сжатые команды ----- */
    {
        uint32_t t0, t1, t2, t3;
        static volatile uint32_t cbuf[4] __attribute__((aligned(4)));

        asm volatile(
            "li a0, 0x0F0F\n"
            "li a1, 0x00FF\n"
            "c.mv a2, a0\n c.sub a2, a1\n"
            "c.mv a3, a0\n c.xor a3, a1\n"
            "c.mv a4, a0\n c.or a4, a1\n"
            "c.mv a5, a0\n c.and a5, a1\n"
            "mv %0, a2\n mv %1, a3\n mv %2, a4\n mv %3, a5\n"
            : "=r"(t0), "=r"(t1), "=r"(t2), "=r"(t3) :: "a0", "a1", "a2", "a3", "a4", "a5");
        check("c.sub", t0, 0x0E10);
        check("c.xor", t1, 0x0FF0);
        check("c.or",  t2, 0x0FFF);
        check("c.and", t3, 0x000F);

        asm volatile(
            "li a0, -64\n c.srai a0, 2\n"
            "li a1, -64\n c.srli a1, 28\n"
            "li a2, 0x1234\n c.andi a2, 0x1f\n"
            "li a3, 3\n c.slli a3, 4\n"
            "mv %0, a0\n mv %1, a1\n mv %2, a2\n mv %3, a3\n"
            : "=r"(t0), "=r"(t1), "=r"(t2), "=r"(t3) :: "a0", "a1", "a2", "a3");
        check("c.srai", t0, 0xFFFFFFF0);
        check("c.srli", t1, 0x0000000F);
        check("c.andi", t2, 0x00000014);
        check("c.slli", t3, 0x00000030);

        asm volatile(
            "mv a5, sp\n"
            "c.addi4spn a4, sp, 16\n"
            "sub a4, a4, a5\n"
            "mv a3, sp\n"
            "c.addi16sp sp, -32\n"
            "mv a2, sp\n"
            "c.addi16sp sp, 32\n"
            "sub a2, a3, a2\n"
            "mv %0, a4\n mv %1, a2\n"
            : "=r"(t0), "=r"(t1) :: "a2", "a3", "a4", "a5");
        check("c.addi4spn", t0, 16);
        check("c.addi16sp", t1, 32);

        asm volatile(
            "c.lui a0, 5\n c.li a1, -3\n c.nop\n"
            "mv %0, a0\n mv %1, a1\n"
            : "=r"(t0), "=r"(t1) :: "a0", "a1");
        check("c.lui", t0, 0x5000);
        check("c.li",  t1, 0xFFFFFFFD);

        asm volatile(
            "li a0, 0\n"
            "c.beqz a0, 1f\n"
            "li a0, 99\n"
            "1:\n"
            "c.bnez a0, 2f\n"
            "c.addi a0, 5\n"
            "2:\n"
            "c.j 3f\n"
            "c.addi a0, 20\n"
            "3:\n"
            "mv %0, a0\n"
            : "=r"(t0) :: "a0");
        check("c.branch", t0, 5);

        asm volatile(
            "li a0, 0\n"
            "c.jal 1f\n"
            "c.j 2f\n"
            "1:\n"
            "c.addi a0, 7\n"
            "c.jr ra\n"
            "2:\n"
            "mv %0, a0\n"
            : "=r"(t0) :: "a0", "ra");
        check("c.jal/jr", t0, 7);

        asm volatile(
            "mv a1, %2\n"
            "li a0, 0x12345678\n"
            "c.sw a0, 4(a1)\n"
            "c.lw a2, 4(a1)\n"
            "mv %0, a2\n"
            "addi sp, sp, -16\n"
            "li a0, 0x5A5A1234\n"
            "c.swsp a0, 8(sp)\n"
            "c.lwsp a3, 8(sp)\n"
            "addi sp, sp, 16\n"
            "mv %1, a3\n"
            : "=r"(t0), "=r"(t1) : "r"(cbuf) : "a0", "a1", "a2", "a3", "memory");
        check("c.lw/sw", t0, 0x12345678);
        check("c.lwsp/swsp", t1, 0x5A5A1234);

        /* 32-битная команда на стыке слов: c.nop (2 байта) + addi a0, zero, 123 */
        asm volatile(
            ".balign 4\n"
            "c.nop\n"
            ".2byte 0x0513, 0x07B0\n"
            "mv %0, a0\n"
            : "=r"(t0) :: "a0");
        check("odd fetch", t0, 123);
    }
    if (fails == 0) puts_("SELFTEST PASS\n");
    else { puts_("SELFTEST FAIL\n"); }
    EXIT = 0x5555;
    for (;;) {}
}