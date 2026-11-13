/* Виртуальная машина ПТ (байткод PTBC v1). Только stdint, без libc: собирается и на ПК, и на RV32. */
#ifndef PTVM_H
#define PTVM_H

#include <stdint.h>

#define PTVM_DS_SIZE 256   /* глубина стека данных (ячеек) */
#define PTVM_RS_SIZE 128   /* глубина стека возвратов */

enum {
    VM_HALT       = 0,     /* штатное завершение (команда HALT) */
    VM_ERR_BADOP  = -1,    /* неизвестная или оборванная команда */
    VM_ERR_DS_OVER  = -2,  /* переполнение стека данных */
    VM_ERR_DS_UNDER = -3,  /* на стеке данных не хватает значений */
    VM_ERR_RS_OVER  = -4,  /* переполнение стека возвратов */
    VM_ERR_RS_UNDER = -5,  /* RET при пустом стеке возвратов */
    VM_ERR_MEM    = -6,    /* адрес вне памяти */
    VM_ERR_DIV0   = -7,    /* деление на ноль */
    VM_ERR_JUMP   = -8,    /* переход за пределы кода */
    VM_ERR_STEPS  = -9,    /* исчерпан лимит шагов */
    VM_ERR_IMAGE  = -10,   /* повреждённый образ программы */
    VM_ERR_SYS    = -11,   /* системный вызов не поддерживается */
    VM_ERR_FRAME  = -12,   /* ошибка кадра локальных переменных */
    VM_ERR_TRAP   = -13    /* программа сама остановила себя командой TRAP (код в trap_code) */
};

struct vm;
/* Системный вызов n. Возвращает 0, чтобы продолжить, или код ошибки (< 0). */
typedef int (*vm_sys_fn)(struct vm *vm, uint8_t n, void *user);

typedef struct vm {
    const uint8_t *code;  uint32_t code_len;
    uint8_t       *mem;   uint32_t mem_len;
    uint32_t pc;
    int32_t  ds[PTVM_DS_SIZE];  uint32_t sp;   /* sp = число значений на стеке */
    uint32_t rs[PTVM_RS_SIZE];  uint32_t rp;
    uint32_t fp, fp_top, heap_end;             /* кадры растут вниз от fp_top, куча вверх от данных до heap_end */
    uint32_t trap_code;
    vm_sys_fn sys;  void *user;
} vm_t;

/* Разбирает образ (заголовок + код + данные), копирует данные в mem с адреса 0,
   остальную память обнуляет. Возвращает 0 или VM_ERR_IMAGE. */
int vm_load(vm_t *vm, const uint8_t *image, uint32_t len, uint8_t *mem, uint32_t mem_len);

/* Выполняет программу. max_steps = 0 значит без лимита. Возвращает VM_HALT или код ошибки. */
int vm_run(vm_t *vm, uint32_t max_steps);

/* Для системных вызовов: положить значение на стек / снять со стека. 0 или код ошибки. */
int vm_push(vm_t *vm, int32_t v);
int vm_pop(vm_t *vm, int32_t *v);

#endif