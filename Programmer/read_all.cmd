@echo off
py fe-prog.py -rd 2000,400 -p 80 -s com3 -f nvram.bin
py fe-prog.py -rd 4000,4000 -p 03 -s com3 -f lib.bin
py fe-prog.py -rd 8000,4000 -p 03 -s com3 -f app.bin
py fe-prog.py -rp 0,1000 -p 00 -s com3 -f boot.bin
