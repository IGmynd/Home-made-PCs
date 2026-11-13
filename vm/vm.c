#include "vm.h"

enum {
    OP_HALT = 0x00, OP_PUSH8 = 0x01, OP_PUSH32 = 0x02, OP_DUP = 0x03, OP_DROP = 0x04,
    OP_SWAP = 0x05, OP_OVER = 0x06,
    OP_ADD = 0x10, OP_SUB = 0x11, OP_MUL = 0x12, OP_DIV = 0x13, OP_MOD = 0x14,
    OP_AND = 0x15, OP_OR = 0x16, OP_XOR = 0x17, OP_SHL = 0x18, OP_SHR = 0x19,
    OP_SAR = 0x1A, OP_NEG = 0x1B, OP_NOT = 0x1C,
    OP_EQ = 0x20, OP_NE = 0x21, OP_LT = 0x22, OP_LE = 0x23, OP_GT = 0x24, OP_GE = 0x25,
    OP_LD32 = 0x30, OP_ST32 = 0x31, OP_LD8 = 0x32, OP_ST8 = 0x33,
    OP_JMP = 0x40, OP_JZ = 0x41, OP_JNZ = 0x42, OP_CALL = 0x43, OP_RET = 0x44,
    OP_SYS = 0x50, OP_TRAP = 0x51, OP_ALLOC = 0x52,
    OP_FRAME = 0x60, OP_LEAVE = 0x61, OP_LDL = 0x62, OP_STL = 0x63
};

static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

int vm_push(vm_t *vm, int32_t v) {
    if (vm->sp >= PTVM_DS_SIZE) return VM_ERR_DS_OVER;
    vm->ds[vm->sp++] = v;
    return 0;
}

int vm_pop(vm_t *vm, int32_t *v) {
    if (vm->sp == 0) return VM_ERR_DS_UNDER;
    *v = vm->ds[--vm->sp];
    return 0;
}

int vm_load(vm_t *vm, const uint8_t *img, uint32_t len, uint8_t *mem, uint32_t mem_len) {
    if (len < 16 || img[0] != 'P' || img[1] != 'T' || img[2] != 'B' || img[3] != 'C') return VM_ERR_IMAGE;
    uint32_t version = img[4] | ((uint32_t)img[5] << 8);
    uint32_t code_len = rd32(img + 8), data_len = rd32(img + 12);
    if (version != 1) return VM_ERR_IMAGE;
    if ((uint64_t)16 + code_len + data_len > len) return VM_ERR_IMAGE;
    if (data_len > mem_len) return VM_ERR_IMAGE;

    vm->code = img + 16;
    vm->code_len = code_len;
    vm->mem = mem;
    vm->mem_len = mem_len;
    for (uint32_t i = 0; i < mem_len; i++) mem[i] = 0;
    for (uint32_t i = 0; i < data_len; i++) mem[i] = img[16 + code_len + i];
    vm->pc = 0; vm->sp = 0; vm->rp = 0;
    vm->fp_top = mem_len & ~3u;
    vm->fp = vm->fp_top;
    vm->heap_end = (data_len + 3u) & ~3u;
    vm->trap_code = 0;
    return 0;
}

static int mem_ok(const vm_t *vm, uint32_t addr, uint32_t size) {
    return size <= vm->mem_len && addr <= vm->mem_len - size;
}

#define POP(x)  do { if (vm->sp == 0) return VM_ERR_DS_UNDER; (x) = vm->ds[--vm->sp]; } while (0)
#define PUSH(x) do { if (vm->sp >= PTVM_DS_SIZE) return VM_ERR_DS_OVER; vm->ds[vm->sp++] = (x); } while (0)
#define U(x)    ((uint32_t)(x))

int vm_run(vm_t *vm, uint32_t max_steps) {
    uint32_t steps = 0;
    for (;;) {
        if (max_steps && steps++ >= max_steps) return VM_ERR_STEPS;
        if (vm->pc >= vm->code_len) return VM_ERR_JUMP;
        uint8_t op = vm->code[vm->pc++];
        int32_t a, b;
        uint32_t t;

        switch (op) {
        case OP_HALT: return VM_HALT;

        case OP_PUSH8:
            if (vm->pc + 1 > vm->code_len) return VM_ERR_BADOP;
            PUSH((int32_t)(int8_t)vm->code[vm->pc]);
            vm->pc += 1;
            break;
        case OP_PUSH32:
            if ((uint64_t)vm->pc + 4 > vm->code_len) return VM_ERR_BADOP;
            PUSH((int32_t)rd32(vm->code + vm->pc));
            vm->pc += 4;
            break;
        case OP_DUP:  POP(a); PUSH(a); PUSH(a); break;
        case OP_DROP: POP(a); break;
        case OP_SWAP: POP(b); POP(a); PUSH(b); PUSH(a); break;
        case OP_OVER: POP(b); POP(a); PUSH(a); PUSH(b); PUSH(a); break;

        case OP_ADD: POP(b); POP(a); PUSH((int32_t)(U(a) + U(b))); break;
        case OP_SUB: POP(b); POP(a); PUSH((int32_t)(U(a) - U(b))); break;
        case OP_MUL: POP(b); POP(a); PUSH((int32_t)(U(a) * U(b))); break;
        case OP_DIV:
            POP(b); POP(a);
            if (b == 0) return VM_ERR_DIV0;
            PUSH(b == -1 ? (int32_t)(0u - U(a)) : a / b);
            break;
        case OP_MOD:
            POP(b); POP(a);
            if (b == 0) return VM_ERR_DIV0;
            PUSH(b == -1 ? 0 : a % b);
            break;
        case OP_AND: POP(b); POP(a); PUSH(a & b); break;
        case OP_OR:  POP(b); POP(a); PUSH(a | b); break;
        case OP_XOR: POP(b); POP(a); PUSH(a ^ b); break;
        case OP_SHL: POP(b); POP(a); PUSH((int32_t)(U(a) << (U(b) & 31))); break;
        case OP_SHR: POP(b); POP(a); PUSH((int32_t)(U(a) >> (U(b) & 31))); break;
        case OP_SAR: POP(b); POP(a); PUSH(a >> (U(b) & 31)); break;
        case OP_NEG: POP(a); PUSH((int32_t)(0u - U(a))); break;
        case OP_NOT: POP(a); PUSH(~a); break;

        case OP_EQ: POP(b); POP(a); PUSH(a == b); break;
        case OP_NE: POP(b); POP(a); PUSH(a != b); break;
        case OP_LT: POP(b); POP(a); PUSH(a <  b); break;
        case OP_LE: POP(b); POP(a); PUSH(a <= b); break;
        case OP_GT: POP(b); POP(a); PUSH(a >  b); break;
        case OP_GE: POP(b); POP(a); PUSH(a >= b); break;

        case OP_LD32:                        /* ( addr -- значение ) */
            POP(a); t = U(a);
            if (!mem_ok(vm, t, 4)) return VM_ERR_MEM;
            PUSH((int32_t)rd32(vm->mem + t));
            break;
        case OP_ST32:                        /* ( значение addr -- ) */
            POP(a); POP(b); t = U(a);
            if (!mem_ok(vm, t, 4)) return VM_ERR_MEM;
            vm->mem[t]     = (uint8_t)(U(b));
            vm->mem[t + 1] = (uint8_t)(U(b) >> 8);
            vm->mem[t + 2] = (uint8_t)(U(b) >> 16);
            vm->mem[t + 3] = (uint8_t)(U(b) >> 24);
            break;
        case OP_LD8:
            POP(a); t = U(a);
            if (!mem_ok(vm, t, 1)) return VM_ERR_MEM;
            PUSH(vm->mem[t]);
            break;
        case OP_ST8:
            POP(a); POP(b); t = U(a);
            if (!mem_ok(vm, t, 1)) return VM_ERR_MEM;
            vm->mem[t] = (uint8_t)b;
            break;

        case OP_JMP: case OP_JZ: case OP_JNZ: case OP_CALL: {
            if ((uint64_t)vm->pc + 4 > vm->code_len) return VM_ERR_BADOP;
            uint32_t target = rd32(vm->code + vm->pc);
            vm->pc += 4;
            int take = 1;
            if (op == OP_JZ)  { POP(a); take = (a == 0); }
            if (op == OP_JNZ) { POP(a); take = (a != 0); }
            if (!take) break;
            if (target >= vm->code_len) return VM_ERR_JUMP;
            if (op == OP_CALL) {
                if (vm->rp >= PTVM_RS_SIZE) return VM_ERR_RS_OVER;
                vm->rs[vm->rp++] = vm->pc;
            }
            vm->pc = target;
            break;
        }
        case OP_RET:
            if (vm->rp == 0) return VM_ERR_RS_UNDER;
            vm->pc = vm->rs[--vm->rp];
            break;

        case OP_SYS: {
            if (vm->pc + 1 > vm->code_len) return VM_ERR_BADOP;
            uint8_t n = vm->code[vm->pc++];
            if (!vm->sys) return VM_ERR_SYS;
            int r = vm->sys(vm, n, vm->user);
            if (r != 0) return r;
            break;
        }

        case OP_TRAP:                        /* остановка с кодом: «индекс вне списка» и тому подобное */
            if (vm->pc + 1 > vm->code_len) return VM_ERR_BADOP;
            vm->trap_code = vm->code[vm->pc++];
            return VM_ERR_TRAP;

        case OP_ALLOC: {                     /* ( байты -- адрес ) выделяет и обнуляет память кучи */
            POP(a);
            if (a < 0) return VM_ERR_MEM;
            uint64_t need = ((uint64_t)(uint32_t)a + 3u) & ~(uint64_t)3u;
            if ((uint64_t)vm->heap_end + need > vm->fp) return VM_ERR_MEM;
            uint32_t addr = vm->heap_end;
            for (uint32_t i = 0; i < (uint32_t)need; i++) vm->mem[addr + i] = 0;
            vm->heap_end += (uint32_t)need;
            PUSH((int32_t)addr);
            break;
        }

        case OP_FRAME: {                     /* n слотов; заголовок кадра: [прежний fp][n] */
            if (vm->pc + 1 > vm->code_len) return VM_ERR_BADOP;
            uint32_t n = vm->code[vm->pc++];
            uint32_t size = 4u * (n + 2u);
            if (vm->fp < vm->heap_end || vm->fp - vm->heap_end < size) return VM_ERR_FRAME;
            uint32_t nf = vm->fp - size;
            for (uint32_t i = 8; i < size; i++) vm->mem[nf + i] = 0;      /* слоты обнуляем */
            vm->mem[nf]     = (uint8_t)vm->fp;
            vm->mem[nf + 1] = (uint8_t)(vm->fp >> 8);
            vm->mem[nf + 2] = (uint8_t)(vm->fp >> 16);
            vm->mem[nf + 3] = (uint8_t)(vm->fp >> 24);
            vm->mem[nf + 4] = (uint8_t)n;
            vm->mem[nf + 5] = vm->mem[nf + 6] = vm->mem[nf + 7] = 0;
            vm->fp = nf;
            break;
        }
        case OP_LEAVE: {
            if (vm->fp >= vm->fp_top) return VM_ERR_FRAME;
            uint32_t old = rd32(vm->mem + vm->fp);
            if (old <= vm->fp || old > vm->fp_top || (old & 3u)) return VM_ERR_FRAME;
            vm->fp = old;
            break;
        }
        case OP_LDL: case OP_STL: {
            if (vm->pc + 1 > vm->code_len) return VM_ERR_BADOP;
            uint32_t i = vm->code[vm->pc++];
            if (vm->fp >= vm->fp_top) return VM_ERR_FRAME;
            if (i >= rd32(vm->mem + vm->fp + 4)) return VM_ERR_FRAME;
            uint32_t addr = vm->fp + 8u + 4u * i;
            if (!mem_ok(vm, addr, 4)) return VM_ERR_FRAME;     /* заголовок кадра могли испортить */
            if (op == OP_LDL) {
                PUSH((int32_t)rd32(vm->mem + addr));
            } else {
                POP(a);
                vm->mem[addr]     = (uint8_t)(U(a));
                vm->mem[addr + 1] = (uint8_t)(U(a) >> 8);
                vm->mem[addr + 2] = (uint8_t)(U(a) >> 16);
                vm->mem[addr + 3] = (uint8_t)(U(a) >> 24);
            }
            break;
        }

        default: return VM_ERR_BADOP;
        }
    }
}