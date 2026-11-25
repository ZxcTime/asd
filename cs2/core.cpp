// core.cpp — CS2 skin changer (internal x64)
#include <Windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <imgui.h>
#include <imgui_impl_win32.h>
#include <imgui_impl_dx11.h>
#include <MinHook.h>
#include <fstream>
#include <string>
#include <unordered_map>
#include <nlohmann/json.hpp>
#include "offsets.h"

using json = nlohmann::json;
static Offsets g_off;

// ---------- config ----------
struct Skin { int paint=0; float wear=0.0001f; int seed=0; int st=-1; };
struct Config {
    uint32_t account_id = 0;
    bool enabled = false;
    std::unordered_map<int, Skin> skins;
    Skin knife; int knife_defidx = 0; std::string knife_model;
    Skin gloves; int gloves_defidx = 0;
    struct Agent { int defidx=0; std::string model; } agents[2];
    std::unordered_map<uint64_t, std::unordered_map<int, Skin>> sync;

    static Config Load(const std::string& p) {
        Config c; std::ifstream f(p); if (!f) return c;
        json j; f >> j;
        c.account_id = j.value("account_id", 0);
        c.enabled = j.value("enabled", false);
        if (j.contains("skins")) for (auto& [k, v] : j["skins"].items()) {
            Skin s;
            s.paint = v.value("paint_kit", 0);
            s.wear  = v.value("wear", 0.0001f);
            s.seed  = v.value("seed", 0);
            s.st    = v.value("stattrak", -1);
            c.skins[std::stoi(k)] = s;
        }
        if (j.contains("knife")) {
            auto& k = j["knife"];
            c.knife_defidx = k.value("defidx", 0);
            c.knife.paint  = k.value("paint_kit", 0);
            c.knife.wear   = k.value("wear", 0.0001f);
            c.knife.seed   = k.value("seed", 0);
            c.knife.st     = k.value("stattrak", -1);
            c.knife_model  = k.value("model", "");
        }
        if (j.contains("gloves")) {
            auto& g = j["gloves"];
            c.gloves_defidx = g.value("defidx", 0);
            c.gloves.paint  = g.value("paint_kit", 0);
            c.gloves.wear   = g.value("wear", 0.0001f);
        }
        if (j.contains("agents")) {
            int i = 0;
            for (auto& [t, v] : j["agents"].items()) {
                c.agents[i].defidx = v.value("defidx", 0);
                c.agents[i].model  = v.value("model", "");
                if (++i >= 2) break;
            }
        }
        if (j.contains("sync")) for (auto& [sid, v] : j["sync"].items()) {
            for (auto& [d, s] : v["skins"].items()) {
                Skin sk;
                sk.paint = s.value("paint_kit", 0);
                sk.wear  = s.value("wear", 0.0001f);
                sk.seed  = s.value("seed", 0);
                c.sync[std::stoull(sid)][std::stoi(d)] = sk;
            }
        }
        return c;
    }
} g_cfg;

// ---------- memory ----------
template <typename T> static T Read(uintptr_t a) { return *reinterpret_cast<T*>(a); }
template <typename T> static void Write(uintptr_t a, T v) { *reinterpret_cast<T*>(a) = v; }
static uintptr_t Base() { return reinterpret_cast<uintptr_t>(GetModuleHandleA("client.dll")); }

static uintptr_t Ent(int idx) {
    auto list = Read<uintptr_t>(Base() + g_off.dwEntityList);
    if (!list) return 0;
    auto chunk = Read<uintptr_t>(list + 8 * (idx >> 9));
    if (!chunk) return 0;
    return Read<uintptr_t>(chunk + 0x10 * (idx & 0x1FF));
}
static uintptr_t LocalPawn() { return Read<uintptr_t>(Base() + g_off.dwLocalPlayerPawn); }

static uintptr_t WeaponServices(uintptr_t pawn) {
    if (!pawn || !g_off.m_pWeaponServices) return 0;
    return Read<uintptr_t>(pawn + g_off.m_pWeaponServices);
}

static uintptr_t GetEconItemView(uintptr_t econEntity) {
    if (!econEntity || !g_off.m_AttributeManager) return 0;
    return econEntity + g_off.m_AttributeManager + g_off.m_Item;
}
static int16_t GetDefIndex(uintptr_t e) {
    auto iv = GetEconItemView(e);
    return iv ? Read<int16_t>(iv + g_off.m_iItemDefinitionIndex) : 0;
}

static void ApplySkin(uintptr_t e, const Skin& s, bool knife=false) {
    if (!e || !g_off.m_nFallbackPaintKit) return;
    Write<int32_t>(e + g_off.m_nFallbackPaintKit, s.paint);
    Write<int32_t>(e + g_off.m_nFallbackSeed, s.seed);
    Write<float>(e + g_off.m_flFallbackWear, s.wear);
    if (s.st >= 0 && g_off.m_nFallbackStatTrak)
        Write<int32_t>(e + g_off.m_nFallbackStatTrak, s.st);

    auto iv = GetEconItemView(e);
    if (iv) {
        if (g_off.m_iItemIDHigh) Write<int32_t>(iv + g_off.m_iItemIDHigh, -1);
        if (g_off.m_iItemIDLow)  Write<int32_t>(iv + g_off.m_iItemIDLow, 0);
        if (g_off.m_bInitialized) Write<uint8_t>(iv + g_off.m_bInitialized, 1);
        if (knife && g_off.m_iItemDefinitionIndex && g_cfg.knife_defidx)
            Write<int16_t>(iv + g_off.m_iItemDefinitionIndex, (int16_t)g_cfg.knife_defidx);
    }
}

static void ApplyLocal(uintptr_t pawn) {
    if (!pawn) return;
    auto ws = WeaponServices(pawn);
    if (!ws) return;

    if (g_off.m_hMyWeapons) {
        for (int i = 0; i < 64; ++i) {
            auto h = Read<uint32_t>(ws + g_off.m_hMyWeapons + i * 4);
            if (!h || h == 0xFFFFFFFF) continue;
            auto w = Ent(h & 0x1FFF);
            if (!w) continue;
            auto d = GetDefIndex(w);
            if (g_cfg.skins.count(d)) ApplySkin(w, g_cfg.skins[d]);
        }
    }
    if (g_cfg.knife_defidx && g_off.m_hActiveWeapon) {
        auto h = Read<uint32_t>(ws + g_off.m_hActiveWeapon);
        auto w = Ent(h & 0x1FFF);
        if (w && GetDefIndex(w) == g_cfg.knife_defidx)
            ApplySkin(w, g_cfg.knife, true);
    }
    if (g_cfg.gloves_defidx) {
        for (int i = 1; i < 2048; ++i) {
            auto e = Ent(i); if (!e) continue;
            if (GetDefIndex(e) == g_cfg.gloves_defidx)
                ApplySkin(e, g_cfg.gloves);
        }
    }
}

static void ApplyRemote(uintptr_t pawn) {
    if (g_cfg.sync.empty() || !g_off.m_steamID) return;
    auto sid = Read<uint64_t>(pawn + g_off.m_steamID);
    auto it = g_cfg.sync.find(sid);
    if (it == g_cfg.sync.end()) return;
    auto ws = WeaponServices(pawn); if (!ws) return;
    if (g_off.m_hMyWeapons) {
        for (int i = 0; i < 64; ++i) {
            auto h = Read<uint32_t>(ws + g_off.m_hMyWeapons + i * 4);
            if (!h || h == 0xFFFFFFFF) continue;
            auto w = Ent(h & 0x1FFF); if (!w) continue;
            auto d = GetDefIndex(w);
            auto sk = it->second.find(d);
            if (sk != it->second.end()) ApplySkin(w, sk->second);
        }
    }
}

// ---------- hooks ----------
using FSN_t = void(__fastcall*)(void*, int);
static FSN_t oFSN = nullptr;
static void __fastcall hkFSN(void* self, int stage) {
    if (stage == 6 && g_cfg.enabled) {
        auto lp = LocalPawn();
        ApplyLocal(lp);
        for (int i = 1; i <= 64; ++i) {
            auto p = Ent(i);
            if (p && p != lp) ApplyRemote(p);
        }
    }
    oFSN(self, stage);
}

using Present_t = HRESULT(__stdcall*)(IDXGISwapChain*, UINT, UINT);
static Present_t oPresent = nullptr;
static bool g_open = true;

static HRESULT __stdcall hkPresent(IDXGISwapChain* sc, UINT si, UINT fl) {
    static bool init = false;
    if (!init) {
        DXGI_SWAP_CHAIN_DESC d{}; sc->GetDesc(&d);
        ImGui::CreateContext();
        ImGui::StyleColorsDark();
        ImGui_ImplWin32_Init(d.OutputWindow);
        ID3D11Device* dev = nullptr;
        ID3D11DeviceContext* ctx = nullptr;
        sc->GetDevice(__uuidof(ID3D11Device), (void**)&dev);
        dev->GetImmediateContext(&ctx);
        ImGui_ImplDX11_Init(dev, ctx);
        init = true;
    }
    if (GetAsyncKeyState(VK_INSERT) & 1) g_open = !g_open;

    ImGui_ImplDX11_NewFrame();
    ImGui_ImplWin32_NewFrame();
    ImGui::NewFrame();
    if (g_open) {
        ImGui::Begin("cs2 skin changer", &g_open);
        ImGui::Checkbox("enabled", &g_cfg.enabled);
        if (ImGui::Button("reload config")) g_cfg = Config::Load("csgo_skins.json");
        ImGui::Text("skins: %zu", g_cfg.skins.size());
        ImGui::Text("sync friends: %zu", g_cfg.sync.size());
        ImGui::End();
    }
    ImGui::Render();
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
    return oPresent(sc, si, fl);
}

// ---------- init ----------
static void Init() {
    g_off = Offsets::Load("csgo.json");
    g_cfg = Config::Load("csgo_skins.json");
    MH_Initialize();
    // Хуки:
    // FrameStageNotify — vtable[37] у CHLClient (найди через CreateInterface("Source2Client002"))
    // Present — dummy swapchain, vtable[8]
}
BOOL APIENTRY DllMain(HMODULE m, DWORD r, LPVOID) {
    if (r == DLL_PROCESS_ATTACH) { DisableThreadLibraryCalls(m); Init(); }
    return TRUE;
}