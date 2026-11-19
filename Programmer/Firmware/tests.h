#include <stdio.h>

#include "defs.h"
#include "bus.h"
#include "psd.h"
#include "hw.h"

#ifndef TESTS_H
#define TESTS_H

bit write_string_eeprom(uint16_t address, uint8_t *s);
bit write_string_rom(uint16_t address, uint8_t *s);
bit write_string_flash(uint16_t address, uint8_t *s);
void test_write_eeprom(uint16_t start, uint16_t end, uint8_t page, uint8_t *test_num, bit space);
void test_write_flash(uint16_t start, uint16_t end, uint8_t page, uint8_t *test_num);
void test_fill_all(void);
void psd_blinky(uint8_t blinks);

#endif