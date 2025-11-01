@echo off
REM ===========================================
REM Farm Shop – Translation Update Utility
REM ===========================================

echo.
echo 🌍 Extracting new translation strings...
pybabel extract -F babel.cfg -o messages.pot . || goto :error

echo.
echo 🔄 Updating existing translation catalogs...
pybabel update -i messages.pot -d translations || goto :error

echo.
echo 📝 Reminder: edit your .po files if new text was found!
echo    Example: translations\pt\LC_MESSAGES\messages.po

pause

echo.
echo 🧵 Compiling translations to .mo files...
pybabel compile -d translations || goto :error

echo.
echo ✅ All done! Translations have been updated and compiled.
echo.

pause
exit /b 0

:error
echo ❌ An error occurred. Please check the messages above.
pause
exit /b 1
