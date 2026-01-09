@echo off
title Instalacia Faktura Renamer
echo ============================================
echo    INSTALACIA FAKTURA RENAMER
echo ============================================
echo.
echo Tento skript nainstaluje potrebne Python kniznice.
echo.
echo Pred spustenim sa uisti, ze mas nainstalovany:
echo   1. Python (z python.org)
echo   2. Tesseract OCR (z github.com/UB-Mannheim/tesseract/wiki)
echo.
pause

echo.
echo Instalujem kniznice...
echo.
pip install pdfplumber pymupdf Pillow pytesseract

echo.
echo ============================================
if %ERRORLEVEL% == 0 (
    echo    INSTALACIA USPESNA!
    echo.
    echo    Teraz mozes spustit program dvojklikom na:
    echo    Spustit_FakturaRenamer.bat
) else (
    echo    CHYBA PRI INSTALACII
    echo.
    echo    Skontroluj ci mas Python nainstalovany
    echo    a pridany do PATH.
)
echo ============================================
echo.
pause
