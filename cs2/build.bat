@echo off
setlocal
where cl >nul 2>nul
if errorlevel 1 (
    echo [!] Открой "x64 Native Tools Command Prompt for VS 2022" и запусти оттуда.
    pause & exit /b 1
)

if not exist third_party\imgui (
    git clone --depth 1 https://github.com/ocornut/imgui third_party\imgui
)
if not exist third_party\minhook (
    git clone --depth 1 https://github.com/TsudaKageyu/minhook third_party\minhook
)
if not exist third_party\json.hpp (
    powershell -Command "Invoke-WebRequest -Uri https://github.com/nlohmann/json/releases/latest/download/json.hpp -OutFile third_party\json.hpp"
)

cl /nologo /std:c++20 /EHsc /O2 /MT /DNDEBUG /LD ^
   core.cpp ^
   third_party\imgui\imgui.cpp ^
   third_party\imgui\imgui_draw.cpp ^
   third_party\imgui\imgui_tables.cpp ^
   third_party\imgui\imgui_widgets.cpp ^
   third_party\imgui\backends\imgui_impl_win32.cpp ^
   third_party\imgui\backends\imgui_impl_dx11.cpp ^
   third_party\minhook\src\*.c ^
   /I third_party\imgui /I third_party\imgui\backends /I third_party\minhook\include /I third_party ^
   /link d3d11.lib dxgi.lib user32.lib ^
   /OUT:csgo_skins.dll

if errorlevel 1 ( echo [!] Сборка упала. & pause & exit /b 1 )
echo [+] csgo_skins.dll готов.
pause