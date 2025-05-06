@echo off
attrib *.* -r -h -s
echo raps clean for reActPSNv2.00
echo:
echo del act.dat
if exist act.dat del act.dat
echo del *.rif
del *.rif
del *.
echo del *.p3t.edat
del *.p3t.edat
echo:
echo deleting raps with ERRORs...
setlocal
for /f  "usebackq delims=;" %%A in (`dir /b *.rap`) do If %%~zA NEQ 16 (
del %%~fA
echo del %%~fA
)

setlocal enabledelayedexpansion

set /a count_rap=0
for %%1 in (*.rap) do (
set filename=%%1
set fileext=!filename:~36,4!
if not "!fileext!"==".rap" (
echo del !filename!
del "!filename!"
) else set /a count_rap=count_rap+1
)

set /a count_edat=0
for %%1 in (*.edat) do (
set filename=%%1
set fileext=!filename:~36,5!
if not "!fileext!"==".edat" (
echo del !filename!
del "!filename!"
) else set /a count_edat=count_edat+1
)

echo clean completed.
echo:
echo This exdata has !count_rap! raps and !count_edat! edats
pause
