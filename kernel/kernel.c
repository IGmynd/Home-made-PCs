#include <stdint.h>

#define UART (*(volatile uint8_t *)0x10000000)
#define EXIT (*(volatile uint32_t *)0x100000)
#define MTIME_LO (*(volatile uint32_t *)0x0200BFF8)
#define MTIME_HI (*(volatile uint32_t *)0x0200BFFC)
#define CMP_LO (*(volatile uint32_t *)0x02004000)
#define CMP_HI (*(volatile uint32_t *)0x02004004)
#define TICK 1000000u /* 10 МГц * 0.1 с */

#define csr_read(r) ({ uint32_t v; asm volatile("csrr %0, " #r : "=r"(v)); v; })
#define csr_write(r, v) asm volatile("csrw " #r ", %0" ::"r"(v))
#define csr_set(r, v) asm volatile("csrs " #r ", %0" ::"r"(v))

extern void trap_entry(void);
static volatile uint32_t ticks;

static void puts_(const char *s) { while (*s) UART = *s++; }

static void puthex(uint32_t v) {
    for (int i = 28; i >= 0; i -= 4) UART = "0123456789abcdef"[(v >> i) & 15];
}

static uint64_t mtime(void) {
    uint32_t hi, lo;
    do { hi = MTIME_HI; lo = MTIME_LO; } while (hi != MTIME_HI);
    return ((uint64_t)hi << 32) | lo;
}

static void set_timer(uint64_t t) {
    CMP_HI = 0xFFFFFFFFu; /* сначала "в бесконечность", чтобы не словить ложное срабатывание */
    CMP_LO = (uint32_t)t;
    CMP_HI = (uint32_t)(t >> 32);
}

void trap_handler(void) {
    uint32_t cause = csr_read(mcause);
    if (cause & 0x80000000u) {                 /* прерывание */
        if ((cause & 0xFFF) == 7) {            /* таймер */
            ticks++;
            set_timer(mtime() + TICK);
        }
    } else if (cause == 11) {                  /* ecall */
        puts_("ecall caught\n");
        csr_write(mepc, csr_read(mepc) + 4);   /* перешагнуть через ecall */
    } else {
        puts_("unhandled trap, mcause=0x");
        puthex(cause);
        puts_("\n");
        for (;;) {}
    }
}

void main(void) {
    puts_("kernel: alive\n");
    csr_write(mtvec, (uint32_t)trap_entry);

    asm volatile("ecall");                     /* проверка исключения */

    set_timer(mtime() + TICK);
    csr_set(mie, 0x80);                        /* MTIE: разрешить прерывание таймера */
    csr_set(mstatus, 0x8);                     /* MIE: разрешить прерывания глобально */

    uint32_t shown = 0;
    while (shown < 5) {
        asm volatile("wfi");
        while (shown < ticks) {
            shown++;
            puts_("tick ");
            UART = '0' + shown;
            UART = '\n';
        }
    }
    puts_("kernel: done\n");
    EXIT = 0x5555;
}