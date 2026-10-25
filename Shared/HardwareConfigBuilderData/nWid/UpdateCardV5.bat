::#!openn
::#! kind: tool/nwid-update-card
::#! schema: 1
::#! producer: hand-maintained (Shared/HardwareConfigBuilderData/nWid)
::#! generated: 2026-10-26T00:20:00Z
::#! source: FVZ_MSC_20261020_1731/PRODUCTION/HilscherIOCard1/nWid/UpdateCardV4.bat (V4) + the remembered card (V5)
::#! comment: copies this folder's config.nxd and nwid.nxd into the Hilscher card's Channel0; the card chosen is remembered in card.txt
::#!end
@echo off
setlocal enabledelayedexpansion

set currentDir=%~dp0
set cifX_Device_Driver_Path=C:\Program Files\cifX Device Driver
if defined CIFX_DRIVER_PATH set "cifX_Device_Driver_Path=%CIFX_DRIVER_PATH%"
set "cardFile=%currentDir%card.txt"

::the remembered card
set "savedCard="
if exist "%cardFile%" set /p savedCard=<"%cardFile%"
if defined savedCard (
	if exist "%cifX_Device_Driver_Path%\!savedCard!\" (
		echo Hilscher Card !savedCard! found - the card remembered in card.txt
		set "cardFolderPath=%cifX_Device_Driver_Path%\!savedCard!"
		goto :CARD_FOLDER_FOUND
	) else (
		echo The card remembered in card.txt, !savedCard!, is not present in "%cifX_Device_Driver_Path%\" - choosing again
		echo.
	)
)

set /a count=0
for /d %%i in ("%cifX_Device_Driver_Path%\1280100_*") do (
    set /a count+=1
    set "folder!count!=%%i"
)

::none found
if !count! EQU 0 (
    echo No folders starting with "1280100_" found in "%cifX_Device_Driver_Path%\"

	PAUSE
	EXIT /B 1
)

::one found
if !count! EQU 1 (
	echo One Hilscher Card folder starting with 1280100_ found: "!folder1!"

	set cardFolderPath=!folder1!

	PAUSE
	goto :CARD_FOLDER_FOUND
)

::multiple found
if !count! GTR 1 (
	echo Multiple folders starting with "1280100_" found in "%cifX_Device_Driver_Path%\"
	echo.

	set /a index=0

	:LOOP
	set /a index+=1
	call echo !index!. %%folder!index!%%

	if !index! LSS !count! (goto :LOOP)
	@REM end_loop

	echo.
	:INVALID_CHOICE
	set "choice="
	set /p choice="Which one do you want to select? Insert choice:  "
	if "!choice!"=="" (
		echo No choice entered - nothing copied
		exit /b 1
	)

	if !choice! GTR !count! (goto :INVALID_CHOICE)
	if !choice! LSS 1 (goto :INVALID_CHOICE)

	call set cardFolderPath=%%folder!choice!%%
	goto :CARD_FOLDER_FOUND
)


:CARD_FOLDER_FOUND

::remember the card (its folder name = its serial number)
for %%d in ("!cardFolderPath!") do set "cardSerial=%%~nxd"
>"%cardFile%" echo !cardSerial!
echo Card !cardSerial! remembered in card.txt
echo.

::rename .nxd files
ren %currentDir%\c.nxd config.nxd 				2>nul	&ECHO.

ren %currentDir%\c_nwid.nxd nwid.nxd 			2>nul	&ECHO.
ren %currentDir%\config_nwid.nxd nwid.nxd 		2>nul	&ECHO.

::copy to Hischer Card Folder
set /A CopyResult=0

xcopy %currentDir%\config.nxd "%cardFolderPath%\Channel0"  /y /r
::robocopy "%currentDir%" "%cardFolderPath%\Channel0" "config.nxd" /Copy:DATSO /r:3
set /A CopyResult=CopyResult+%ERRORLEVEL% 			&ECHO.

xcopy %currentDir%\nwid.nxd "%cardFolderPath%\Channel0"  /y /r
::robocopy "%currentDir%" "%cardFolderPath%\Channel0" "nwid.nxd" /Copy:DATSO /r:3
set /A CopyResult=CopyResult+%ERRORLEVEL% 			&ECHO.


IF %CopyResult% EQU 0 (
	DEL %currentDir%\config.nxd
	DEL %currentDir%\nwid.nxd

	ECHO *** COPY SUCCESSFUL *** &ECHO.) ELSE (ECHO ### ERROR DURING COPY ### &ECHO.)

pause
