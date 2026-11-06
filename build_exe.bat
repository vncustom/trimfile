@echo off
rem ============================================================================
rem  build_exe.bat - Dong goi Trim file thanh TrimFile.exe (PyInstaller)
rem
rem  Cach dung:   build_exe.bat          -> tao thu muc release\TrimFile\
rem               build_exe.bat zip      -> them release\TrimFile.zip de mang sang may khac
rem
rem  Can: Python 3.10+ (co Tkinter) + internet (lan dau, de tai PyInstaller)
rem       ffmpeg.exe, ffprobe.exe (va ffplay.exe) nam canh file nay
rem  Xem huong dan chi tiet: HUONG_DAN_BUILD_EXE.md
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"

rem ----- Cau hinh -------------------------------------------------------------
set "APP_NAME=TrimFile"
set "VENV=.venv-build"
set "OUT=release\%APP_NAME%"
rem  --onefile : 1 file .exe duy nhat (goi gon)
rem  --onedir  : thu muc (khoi dong nhanh hon, it bi antivirus bao nham hon)
set "MODE=--onefile"
rem ----------------------------------------------------------------------------

echo.
echo === Build %APP_NAME%.exe ===

rem 1. Kiem tra file can thiet
if not exist "trimfile.py" (
  echo [LOI] Khong thay trimfile.py trong thu muc nay.
  goto :fail
)
for %%F in (ffmpeg.exe ffprobe.exe) do (
  if not exist "%%F" (
    echo [LOI] Thieu %%F. Hay chep ffmpeg.exe, ffprobe.exe, ffplay.exe vao thu muc nay.
    goto :fail
  )
)
if not exist "ffplay.exe" echo [CANH BAO] Thieu ffplay.exe - ban build se khong co tieng khi Play.

rem 2. Tim Python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [LOI] Khong tim thay Python. Cai Python 3.10+ tu python.org ^(tick "Add python.exe to PATH"^).
  goto :fail
)
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo [LOI] Python nay khong co Tkinter. Cai lai Python tu python.org ^(giu nguyen muc "tcl/tk and IDLE"^).
  goto :fail
)

rem 3. Tao moi truong build rieng (khong dong vao Python he thong) + cai PyInstaller
if not exist "%VENV%\Scripts\python.exe" (
  echo Tao moi truong build "%VENV%" ...
  %PY% -m venv "%VENV%"
  if errorlevel 1 goto :fail
)
echo Cai/cap nhat PyInstaller ...
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip pyinstaller
if errorlevel 1 (
  echo [LOI] Khong cai duoc PyInstaller. Kiem tra ket noi internet.
  goto :fail
)

rem 4. Build
set "ICONARG="
if exist "app.ico" set "ICONARG=--icon app.ico"
echo Dang build ^(co the mat 1-2 phut^) ...
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean %MODE% --windowed --name %APP_NAME% %ICONARG% --distpath dist --workpath build --specpath build trimfile.py
if errorlevel 1 (
  echo [LOI] PyInstaller bao loi o tren.
  goto :fail
)

rem 5. Gom thanh thu muc phat hanh: exe + ffmpeg + profile
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
if exist "dist\%APP_NAME%.exe" (
  copy /y "dist\%APP_NAME%.exe" "%OUT%\" >nul
) else if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
  xcopy "dist\%APP_NAME%" "%OUT%" /e /i /q /y >nul
) else (
  echo [LOI] Khong tim thay ket qua build trong thu muc dist.
  goto :fail
)
for %%F in (ffmpeg.exe ffprobe.exe ffplay.exe profiles.json README.md) do (
  if exist "%%F" copy /y "%%F" "%OUT%\" >nul
)

rem 6. Nen zip neu co tham so "zip"
if /i "%~1"=="zip" (
  echo Dang nen zip ^(file ffmpeg lon nen can mot luc^) ...
  if exist "release\%APP_NAME%.zip" del /q "release\%APP_NAME%.zip"
  powershell -NoProfile -Command "Compress-Archive -Path '%OUT%' -DestinationPath 'release\%APP_NAME%.zip' -Force"
  if errorlevel 1 (
    echo [LOI] Nen zip that bai.
    goto :fail
  )
)

echo.
echo === XONG ===
echo Thu muc phat hanh: %CD%\%OUT%
if /i "%~1"=="zip" echo File zip         : %CD%\release\%APP_NAME%.zip
if not defined NOPAUSE (
  start "" "%OUT%"
  pause
)
exit /b 0

:fail
echo.
echo Build THAT BAI.
if not defined NOPAUSE pause
exit /b 1
