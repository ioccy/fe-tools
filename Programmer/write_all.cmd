@echo off
py fe-prog.py -we 2000,400 -p 80 -s com3 -f nvram.bin
py fe-prog.py -c 4000 -p 03 -s com3
py fe-prog.py -wf 4000,4000 -p 03 -s com3 -f lib.bin
py fe-prog.py -c 8000 -p 03 -s com3
py fe-prog.py -wf 8000,4000 -p 03 -s com3 -f app.bin
