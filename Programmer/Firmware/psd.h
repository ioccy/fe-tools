#include "defs.h"

#ifndef PSD_H
#define PSD_H

#define CSIOP 0xF000
#define FLASH_ID 0xE3

// EEPROM
void psd_sdp_unlock_full(uint16_t address);
void psd_sdp_unlock_byte(uint16_t address);
bit psd_write_eeprom(uint16_t address, uint8_t value);

//FLASH
bit psd_erase_sector(uint16_t address);
bit psd_clear_flash(uint16_t address);
uint8_t psd_flash_id(uint16_t address);
bit psd_write_flash(uint16_t address, uint8_t value);

// BITBANG
uint8_t psd_read_rom(uint16_t addr);
bit psd_write_rom(uint16_t addr, uint8_t value);

typedef struct REG_8XX_st {
    uint8_t PA_IN;      // 0x00; Reads Port pin as input, MCU I/O input mode
    uint8_t PB_IN;      // 0x01; Reads Port pin as input, MCU I/O input mode
    uint8_t PA_CTRL;    // 0x02; Selects mode between MCU I/O or Address Out
    uint8_t PB_CTRL;    // 0x03; Selects mode between MCU I/O or Address Out
    uint8_t PA_OUT;     // 0x04; Stores data for output to Port pins, MCU I/O output mode
    uint8_t PB_OUT;     // 0x05; Stores data for output to Port pins, MCU I/O output mode
    uint8_t PA_DIR;     // 0x06; Configures Port pin as input or output
    uint8_t PB_DIR;     // 0x07; Configures Port pin as input or output
    uint8_t PA_DRV;     // 0x08; Configures Port pins as either CMOS or Open Drain on some pins, while selecting high slew rate on other pins
    uint8_t PB_DRV;     // 0x09; Configures Port pins as either CMOS or Open Drain on some pins, while selecting high slew rate on other pins
    uint8_t MCA_IN;     // 0x0A; Reads Input Macrocells
    uint8_t MCB_IN;     // 0x0B; Reads Input Macrocells
    uint8_t PA_ENOUT;   // 0x0C; Reads the status of the output enable to the I/O Port driver
    uint8_t PB_ENOUT;   // 0x0D; Reads the status of the output enable to the I/O Port driver
    uint8_t _sp1[2];    // spacer
    uint8_t PC_IN;      // 0x10; Reads Port pin as input, MCU I/O input mode
    uint8_t PD_IN;      // 0x11; Reads Port pin as input, MCU I/O input mode
    uint8_t PC_OUT;     // 0x12; Stores data for output to Port pins, MCU I/O output mode
    uint8_t PD_OUT;     // 0x13; Stores data for output to Port pins, MCU I/O output mode
    uint8_t PC_DIR;     // 0x14; Configures Port pin as input or output
    uint8_t PD_DIR;     // 0x15; Configures Port pin as input or output
    uint8_t PC_DRV;     // 0x16; Configures Port pins as either CMOS or Open Drain on some pins, while selecting high slew rate on other pins
    uint8_t PD_DRV;     // 0x17; Configures Port pins as either CMOS or Open Drain on some pins, while selecting high slew rate on other pins
    uint8_t MCC_IN;     // 0x18; Reads Input Macrocells
    uint8_t _sp2;       // spacer
    uint8_t PC_ENOUT;   // 0x1A; Reads the status of the output enable to the I/O Port driver
    uint8_t PD_ENOUT;   // 0x1B; Reads the status of the output enable to the I/O Port driver
    uint8_t _sp3[4];    // spacer
    uint8_t MCAB_OUT;   // 0x20; READ – reads output of macrocells AB, WRITE – loads macrocell flip-flops
    uint8_t MCBC_OUT;   // 0x21; READ – reads output of macrocells BC, WRITE – loads macrocell flip-flops
    uint8_t MCAB_MASK;  // 0x22; Blocks writing to the Output Macrocells AB
    uint8_t MCBC_MASK;  // 0x23; Blocks writing to the Output Macrocells AB
    uint8_t _sp4[0x8C]; // spacer
    uint8_t PMMR0;      // 0xB0; Power Management Register 0
    uint8_t res1b;      // spacer
    uint8_t PMMR1;      // 0xB2; Power Management Register 1
    uint8_t res1c;      // spacer
    uint8_t PMMR2;      // 0xB4; Power Management Register 2
    uint8_t _sp5[0x0B]; // spacer
    uint8_t FP;         // 0xC0; [Read only] Flash Sector Protection
    uint8_t res1d;      // spacer
    uint8_t EP;         // 0xC2; [Read only] PSD Security and EEPROM Sector Protection
    uint8_t _sp6[4];    // spacer
    uint8_t JTAG_EN;    // 0xC7; Enables JTAG Port
    uint8_t _sp7[0x18]; // spacer
    uint8_t PAGE;       // 0xE0; Page Register
    uint8_t _sp8;       // spacer
    uint8_t VM;         // 0xE2; Places PSD memory areas in Program and/or Data space on an individual basis
    uint8_t _sp9[0x1D]; // spacer
} REG_8XX;

extern xdata volatile REG_8XX PSD;

#endif
