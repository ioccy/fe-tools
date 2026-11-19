#include "defs.h"

#ifndef BUS_H
#define BUS_H

#define SPACE_DATA 1
#define SPACE_CODE 0

uint8_t EMIF_read(uint16_t address);
void EMIF_write(uint16_t address, uint8_t value);

uint8_t bitbang_read(uint16_t addr, bit);
void bitbang_write(uint16_t addr, uint8_t value, bit);

uint8_t bus_read(uint16_t address);
void bus_write(uint16_t address, uint8_t value);

/*
extern uint8_t (*bus_read)(uint16_t);
extern void (*bus_write)(uint16_t, uint8_t);
*/

/*
#ifdef BITBANG
#define bus_read(address) bitbang_read(address)
#define bus_write(address, length) bitbang_write(address, length)
#else
#define bus_read(address) EMIF_read(address)
#define bus_write(address, length) EMIF_write(address, length)
#endif
*/

#endif