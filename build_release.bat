@echo off
setlocal
cd /d "%~dp0"
echo Building MVS Analyzer v1.4.0 for Windows x64...
dotnet restore MvsAnalyzer.csproj
if errorlevel 1 goto error
dotnet publish MvsAnalyzer.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:DebugType=None -p:DebugSymbols=false
if errorlevel 1 goto error
echo.
echo Build completed.
echo EXE folder:
echo %CD%\bin\Release\net8.0-windows\win-x64\publish
pause
exit /b 0
:error
echo.
echo Build failed. Copy the complete error text and send it for review.
pause
exit /b 1
