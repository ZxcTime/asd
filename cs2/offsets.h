#pragma once
#include <cstdint>
#include <fstream>
#include <string>
#include <nlohmann/json.hpp>

struct Offsets {
    uintptr_t dwEntityList = 0, dwLocalPlayerPawn = 0;
    uintptr_t m_pWeaponServices = 0;
    uintptr_t m_hMyWeapons = 0, m_hActiveWeapon = 0;
    uintptr_t m_AttributeManager = 0, m_Item = 0;
    uintptr_t m_iItemDefinitionIndex = 0, m_iItemIDHigh = 0, m_iItemIDLow = 0;
    uintptr_t m_bInitialized = 0;
    uintptr_t m_nFallbackPaintKit = 0, m_nFallbackSeed = 0;
    uintptr_t m_flFallbackWear = 0, m_nFallbackStatTrak = 0;
    uintptr_t m_iTeamNum = 0, m_steamID = 0;

    static Offsets Load(const std::string& path) {
        Offsets o; std::ifstream f(path); if (!f) return o;
        nlohmann::json j; f >> j;
        auto& s = j["signatures"]; auto& n = j["netvars"];
        o.dwEntityList = s.value("dwEntityList", 0);
        o.dwLocalPlayerPawn = s.value("dwLocalPlayerPawn", 0);
        o.m_pWeaponServices = n.value("m_pWeaponServices", 0);
        o.m_hMyWeapons = n.value("m_hMyWeapons", 0);
        o.m_hActiveWeapon = n.value("m_hActiveWeapon", 0);
        o.m_AttributeManager = n.value("m_AttributeManager", 0);
        o.m_Item = n.value("m_Item", 0);
        o.m_iItemDefinitionIndex = n.value("m_iItemDefinitionIndex", 0);
        o.m_iItemIDHigh = n.value("m_iItemIDHigh", 0);
        o.m_iItemIDLow = n.value("m_iItemIDLow", 0);
        o.m_bInitialized = n.value("m_bInitialized", 0);
        o.m_nFallbackPaintKit = n.value("m_nFallbackPaintKit", 0);
        o.m_nFallbackSeed = n.value("m_nFallbackSeed", 0);
        o.m_flFallbackWear = n.value("m_flFallbackWear", 0);
        o.m_nFallbackStatTrak = n.value("m_nFallbackStatTrak", 0);
        o.m_iTeamNum = n.value("m_iTeamNum", 0);
        o.m_steamID = n.value("m_steamID", 0);
        return o;
    }
};