#define UART (*(volatile unsigned char *)0x10000000)
#define EXIT (*(volatile unsigned int *)0x100000)

static void puts_(const char *s) { while (*s) UART = *s++; }

void main(void) {
    puts_("kernel: alive\n");
    EXIT = 0x5555;
}