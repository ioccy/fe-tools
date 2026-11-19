#include <REG51F380.H>
#include <stdio.h>
#include <stdarg.h>

#include "hw.h"
#include "bus.h"
#include "psd.h"
#include "defs.h"
#include "tests.h"

uint8_t upcase(uint8_t byte)
{
    return byte >= 'a' && byte <= 'z' ? byte ^ 0x20 : byte;
}

// Does not write CR LF when gets LF, unlike Keil's putchar()
uint8_t _putchar(uint8_t value)
{
    while (!TI0); TI0 = 0; SBUF0 = value;
    return value;
}

// Dumps memory block in human readable format
void dump_block(uint16_t start, uint16_t length, bit space)
{
    uint32_t address;
    uint8_t data pos, buf[16];
    
    start &= 0xFFF0;
    length = length ? length : 0xFFFF;

    for (address = start ; address < (uint32_t)start + (uint32_t)length; address += 16) {
        for (pos = 0; pos < 16; pos++)
            buf[pos] = (space == SPACE_CODE) ? psd_read_rom(address + pos) : bus_read(address + pos);
        
        printf("%04X: ", (uint16_t)address); for (pos = 0; pos < 16; pos++) printf("%02bX ", buf[pos]);
        printf("    "); for (pos = 0; pos < 16; pos++) putchar(buf[pos] >= 32 && buf[pos] < 127 ? buf[pos] : '.');
        printf("\n");
    }   
}

// Prints prompt and gets up to 3 uint16_t hex values separated by spaces
uint8_t console_prompt(const uint8_t prompt, ...)
{
    uint8_t buffer[16], i, count;
    uint16_t in[3], *out[3];
    va_list data args;
    
    RI0 = 0; putchar(prompt);
    
    if (gets(buffer, sizeof(buffer)) == 0) return 0;
    if (buffer[0] != ' ') return 0; // No first space -> no parameters entered
    
    count = sscanf(buffer, "%X %X %X", &in[0], &in[1], &in[2]);
    if (count == (uint8_t)EOF) return 0;
    
    va_start(args, prompt);
    for (i = 0; i < count; i++) {
        out[i] = va_arg(args, uint16_t *);
        *out[i] = (uint16_t)in[i];
    }
    va_end(args);    
    
    return count;
}

void main(void)
{
    uint16_t address, length;
    bit    (*write_proc)(uint16_t, uint8_t);
    uint8_t (*read_proc)(uint16_t);
    
    PCA0MD &= ~0x40; // WDTE = 0 (clear watchdog timer enable)

    init_ports();
    init_emif();
    init_osc();
    init_uart(115200);
    init_timer();
    
    P_RESET = 0; delay_ms(1); P_RESET = 1; delay_ms(1);

    printf("\nTerminal ready\n\n> ");

    while (1) {
        if (RI0) { // Non-blocking UART poll
            switch (upcase(SBUF0)) {
                
                case 'R': { // READ D|P [ADDR] [LENGTH]
                    putchar(SBUF0); RI0 = 0;
                    switch (upcase(_getkey())) {
                        case 'D': read_proc = bus_read; break;
                        case 'P': read_proc = psd_read_rom; break;
                        default:  read_proc = NULL;
                    }
                    
                    if (!read_proc || console_prompt(SBUF0, &address, &length) != 2) break;
                    do { _putchar(read_proc(address++)); } while (--length); // Zero length = 0x10000
                } break;
                
                case 'W': { // WRITE E|F|P [ADDR] [LENGTH]
                    putchar(SBUF0); RI0 = 0;
                    switch (upcase(_getkey())) {
                        case 'E': write_proc = psd_write_eeprom; break;
                        case 'F': write_proc = psd_write_flash; break;
                        case 'P': write_proc = psd_write_rom; break;
                        default:  write_proc = NULL;
                    }

                    if (!write_proc || console_prompt(SBUF0, &address, &length) != 2) break;
                    while (length--) {
                        if (!write_proc(address, _getkey())) break;
                        _putchar((write_proc == psd_write_rom) ? psd_read_rom(address) : bus_read(address));
                        address++;
                    }
                } break;                
                
                case 'C': { // CLEAR FLASH BLOCK [ADDR]
                    if (console_prompt(SBUF0, &address) != 1) break;
                    psd_erase_sector(address);
                } break;
                    
                case 'P': { // PAGE [PAGE]
                    if (console_prompt(SBUF0, &address) != 1) break;
                    PSD.PAGE = (uint8_t)address;
                } break;
                
                #ifdef DEBUG
                
                case 'I': { // INFO
                    console_prompt(SBUF0);
                    printf("Flash id: 0x%02bX\n", psd_flash_id(0x4000));
                    printf("Current page: 0x%02bX\n", PSD.PAGE);
                    printf("VM register: 0x%02bX\n", PSD.VM);
                    printf("Flash read-only areas: %s\n", PSD.FP ? "Yes" : "No");
                    printf("EEPROM read-only areas: %s\n", PSD.EP ? "Yes" : "No");
                    // Add port status and VM decode

                } break;
                
                case 'T': { // TEST
                    console_prompt(SBUF0);
                    test_fill_all();
                    psd_blinky(3);
                } break;
                
                case 'D': { // DUMP [ADDR] [LENGTH]
                    if (console_prompt(SBUF0, &address, &length) != 2) break;
                    dump_block(address, length, SPACE_DATA);
                } break;     

                #endif

                default: { // BAD COMMAND
                } break;
            }
            RI0 = 0;
            printf("\n> ");
        }
    }
}