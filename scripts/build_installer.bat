@echo off
echo Building Stream Tool...

cd ..
if errorlevel 1 goto error

echo Cleaning old build folders...
rmdir /s /q build
rmdir /s /q dist

echo Installing Node.js dependencies...
call npm install
if errorlevel 1 goto error

echo Building Node server...
call npx pkg server.js --targets "node18-win-x64" --output dist\server.exe --config package.json
if errorlevel 1 goto error

echo Building Python GUI...
call pyinstaller --clean gui.spec
if errorlevel 1 goto error

echo Build complete! Check the /dist folder.
pause
exit /b

:error
echo An error occurred during the build.
pause
