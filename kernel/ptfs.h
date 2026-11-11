/* PTFS v1: плоская файловая система только для чтения (см. tools/mkfs.py).
   Лежит в области образа носителя класса «данные», каждый файл проверяется по CRC32. */
#ifndef PTFS_H
#define PTFS_H

#include <stdint.h>

#define PTFS_MAX_FILES 15
#define PTFS_T_DATA     0
#define PTFS_T_BYTECODE 1
#define PTFS_T_TEXT     2

enum {
    PTFS_OK = 0,
    PTFS_ERR_MEDIA   = -1,  /* нет носителя или не наш заголовок */
    PTFS_ERR_HDR_CRC = -2,  /* заголовок носителя повреждён */
    PTFS_ERR_EMPTY   = -3,  /* в носителе нет образа */
    PTFS_ERR_MAGIC   = -4,  /* нет файловой системы PTFS */
    PTFS_ERR_COUNT   = -5,  /* некорректный каталог */
    PTFS_ERR_NOFILE  = -6,  /* файла нет */
    PTFS_ERR_SIZE    = -7,  /* файл не влезает в буфер или выходит за носитель */
    PTFS_ERR_CRC     = -8   /* содержимое файла повреждено */
};

typedef struct {
    char     name[17];
    uint8_t  type;
    uint32_t start, size, crc;
} ptfs_entry;

/* Читает один сектор (512 байт) носителя. Реализует ядро (или тест). */
extern void media_read(uint32_t lba, uint8_t *dst);

int ptfs_mount(void);
int ptfs_count(void);
int ptfs_get(int i, ptfs_entry *e);
int ptfs_find(const char *name, ptfs_entry *e);
/* Читает файл в dst целиком секторами: cap должен быть не меньше размера, округлённого до 512. */
int ptfs_read(const ptfs_entry *e, uint8_t *dst, uint32_t cap);

#endif