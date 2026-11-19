#include <REG51F380.H>
#include "tests.h"


bit write_string_eeprom(uint16_t address, uint8_t *s)
{
    uint16_t i = 0;
    while (s[i]) {
        if (!psd_write_eeprom(address + i, s[i])) return 0;
        i++;
    }
    return 1;
}

bit write_string_rom(uint16_t address, uint8_t *s)
{
    uint16_t i = 0;
    while (s[i]) {
        if (!psd_write_rom(address + i, s[i])) return 0;
        i++;
    }
    return 1;
}

bit write_string_flash(uint16_t address, uint8_t *s)
{
    uint16_t i = 0;
    while (s[i]) {
        if (!psd_write_flash(address + i, s[i])) return 0;
        i++;
    }
    return 1;
}

void test_write_eeprom(uint16_t start, uint16_t end, uint8_t page, uint8_t *test_num, bit space)
{
    uint16_t address;
    uint8_t s[17];
    bit (*write_proc)(uint16_t, uint8_t*);
    
    write_proc = (space == SPACE_DATA ? write_string_eeprom : write_string_rom);
    
    for (address = start; address <= (end - 0x0010); address += 0x0010)
    {
        /*
        if ((address & 0xF000) == address) {
            printf("\nUnlocking EEPROM @ 0x%04X\n", address);
            psd_sdp_unlock_full(address);
        }
        */
        
        sprintf(s, "*EP%s-0x%02bX-%04X*", test_num, page, address);
        if (address == (address & 0xF000)) printf("\nWriting EEPROM @ 0x%04X ", address);
        if (!(address % 64)) printf(".");
        if (!write_proc(address, s)) {
            printf("\nEEPROM write error\n");
            return;
        }
    }
    printf("\n");
}

void test_write_flash(unsigned int start, unsigned int end, uint8_t page, uint8_t *test_num)
{
    uint16_t address;
    uint8_t s[17];
    
    for (address = start; address <= (end - 0x0010); address += 0x0010)
    {
        sprintf(s, "*FL%s-0x%02bX-%04X*", test_num, page, address);
        if (address == (address & 0xF000)) printf("Writing Flash @ 0x%04X\n", address);
        if (!write_string_flash(address, s)) {
            printf("Flash write error at %04X\n", address);
            return;
        }
    }
}

void test_fill_all(void)
{
    printf("\nSetting page 0x80\n");PSD.PAGE = 0x80;

    test_write_eeprom(0x2000, 0x4000, 0x80, "11", SPACE_DATA);
    
    printf("\nErasing flash sector... "); printf("%s\n", psd_erase_sector(0x4000) ? "ok" : "fail");
    test_write_flash(0x4000, 0x8000, 0x80, "11");
    
    printf("\nErasing flash sector... "); printf("%s\n", psd_erase_sector(0x8000) ? "ok" : "fail");
    test_write_flash(0x8000, 0xC000, 0x80, "12");
    
    printf("\nErasing flash sector... "); printf("%s\n", psd_erase_sector(0xC000) ? "ok" : "fail");
    test_write_flash(0xC000, 0xF000, 0x80, "13");
    test_write_flash(0xF100, 0xFFFF, 0x80, "13");
    
    printf("\nSetting page 0x03\n"); PSD.PAGE = 0x03;
    
    printf("\nErasing flash sector... "); printf("%s\n", psd_erase_sector(0x8000) ? "ok" : "fail");
    test_write_flash(0x8000, 0xC000, 0x03, "14");

    printf("\nWriting program memory (slow)\n");
    test_write_eeprom(0x0800, 0x2000, 0xFF, "PA", SPACE_CODE);

}

void psd_blinky(uint8_t blinks)
{
    PSD.PA_OUT = PSD.PB_OUT = 0x00;  // All pins Data Out. No need in this if port is IN
    PSD.PA_DIR = PSD.PB_DIR = 0xFF;  // Direction: FF for all pins OUT, 00 for IN

    while (blinks--)
    {
        PSD.PA_OUT = PSD.PB_OUT = 0xFF; delay_ms(500);
        PSD.PA_OUT = PSD.PB_OUT = 0x00; delay_ms(500);
    }
}
