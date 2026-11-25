"""
Builds catalog.json (every weapon / knife / glove with all its skins) from the
game files of YOUR installation, so IDs are always real and match your build.

    python build_catalog.py --csgo "C:/.../Counter-Strike Global Offensive/game/csgo"
or, with extracted files:
    python build_catalog.py --items-game items_game.txt --lang csgo_english.txt

If the files are packed only in pak01_dir.vpk:  pip install vpk
"""
import argparse
import json
import re
import sys
from pathlib import Path

class CatalogError(Exception):
    pass


ITEMS_REL = "scripts/items/items_game.txt"
LANG_RELS = ["resource/csgo_russian.txt", "resource/csgo_english.txt"]
LANG_REL = LANG_RELS[-1]

CATEGORIES = {
    "Пистолеты": ["deagle", "elite", "fiveseven", "glock", "hkp2000", "p250", "tec9",
                  "cz75a", "usp_silencer", "revolver"],
    "Винтовки": ["ak47", "aug", "famas", "galilar", "m4a1", "m4a1_silencer", "sg556"],
    "Снайперские": ["awp", "g3sg1", "scar20", "ssg08"],
    "ПП": ["mac10", "mp5sd", "mp7", "mp9", "bizon", "p90", "ump45"],
    "Тяжёлые": ["m249", "mag7", "negev", "nova", "sawedoff", "xm1014"],
}
ORDER = ["Винтовки", "Пистолеты", "ПП", "Снайперские", "Тяжёлые", "Ножи", "Перчатки", "Агенты"]


def decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_kv(text: str) -> dict:
    pos, n = 0, len(text)
    esc = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}

    def skip():
        nonlocal pos
        while pos < n:
            c = text[pos]
            if c in " \t\r\n\ufeff":
                pos += 1
            elif text.startswith("//", pos):
                while pos < n and text[pos] != "\n":
                    pos += 1
            elif c == "[":
                end = text.find("]", pos)
                pos = n if end == -1 else end + 1
            else:
                break

    def read_str():
        nonlocal pos
        if text[pos] == '"':
            pos += 1
            out = []
            while pos < n and text[pos] != '"':
                if text[pos] == "\\" and pos + 1 < n:
                    out.append(esc.get(text[pos + 1], text[pos + 1]))
                    pos += 2
                else:
                    out.append(text[pos])
                    pos += 1
            pos += 1
            return "".join(out)
        start = pos
        while pos < n and text[pos] not in ' \t\r\n{}"':
            pos += 1
        return text[start:pos]

    def read_obj():
        nonlocal pos
        d = {}
        while True:
            skip()
            if pos >= n:
                return d
            if text[pos] == "}":
                pos += 1
                return d
            key = read_str()
            skip()
            if pos < n and text[pos] == "{":
                pos += 1
                val = read_obj()
                if isinstance(d.get(key), dict):
                    d[key].update(val)
                else:
                    d[key] = val
            else:
                d[key] = read_str()

    return read_obj()


def candidates(explicit, csgo, rel, notes):
    if explicit:
        try:
            yield str(explicit), Path(explicit).read_bytes()
        except OSError as e:
            notes.append(f"cannot read {explicit}: {e}")
        return
    if not csgo:
        return
    csgo = Path(csgo)
    if (csgo / "csgo").is_dir() and not (csgo / "scripts").is_dir():
        csgo = csgo / "csgo"
    loose = csgo / rel
    if loose.exists():
        yield str(loose), loose.read_bytes()
    for pak in sorted(csgo.glob("pak01_dir.vpk")):
        try:
            import vpk
        except ImportError:
            notes.append(f"{pak.name} exists but module 'vpk' is missing: run  pip install vpk")
            continue
        try:
            yield f"{pak}::{rel}", vpk.open(str(pak))[rel].read()
        except Exception as e:
            notes.append(f"could not read {rel} from {pak}: {e}")


MIN_ITEMS = 50
INTERNAL_NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")


def looks_internal(name) -> bool:
    return bool(INTERNAL_NAME.match(name or ""))


def load_items_game(explicit, csgo):
    notes = []
    for label, data in candidates(explicit, csgo, ITEMS_REL, notes):
        ig = parse_kv(decode(data)).get("items_game")
        n = len(ig.get("items", {})) if isinstance(ig, dict) else 0
        if n >= MIN_ITEMS and "alternate_icons2" in ig and "paint_kits" in ig:
            return ig, label
        top = {k: (len(v) if isinstance(v, dict) else "str") for k, v in (ig or {}).items()}
        notes.append(f"{label}: unusable (items={n}); top-level sections: {top}")
    raise CatalogError("no usable items_game.txt found.\n" + "\n".join(notes))


def load_source(explicit, csgo, rel) -> bytes:
    notes = []
    for _, data in candidates(explicit, csgo, rel, notes):
        return data
    raise CatalogError(f"cannot find {rel}. " + " ".join(notes))


def load_tokens(explicit, csgo):
    if explicit:
        return ({k.lower(): v for k, v in
                 ci_get_tokens(parse_kv(decode(Path(explicit).read_bytes()))).items()},
                [str(explicit)])
    tokens, sources = {}, []
    for rel in LANG_RELS:
        try:
            data = load_source(None, csgo, rel)
        except CatalogError:
            continue
        part = ci_get_tokens(parse_kv(decode(data)))
        tokens.update({k.lower(): v for k, v in part.items() if k.lower() not in tokens})
        sources.append(rel)
    return tokens, sources


def ci_get(langkv, key):
    return next((v for k, v in langkv.items()
                 if isinstance(v, dict) and k.lower() == key.lower()), {})


def ci_get_tokens(langkv):
    return ci_get(ci_get(langkv, "lang"), "Tokens")


def pget(item, key, prefabs, depth=0):
    if key in item:
        return item[key]
    if depth > 8:
        return None
    for p in str(item.get("prefab", "")).split():
        pf = prefabs.get(p)
        if isinstance(pf, dict):
            v = pget(pf, key, prefabs, depth + 1)
            if v is not None:
                return v
    return None


def build_catalog(csgo=None, items_game=None, lang=None) -> dict:
    ig, src = load_items_game(items_game, csgo)
    print(f"[catalog] items_game from {src}")
    tokens, lang_src = load_tokens(lang, csgo)
    print(f"[catalog] language tokens loaded: {len(tokens)} from {lang_src}")
    if not tokens:
        print("[catalog] WARNING: no language tokens, skin names will be internal ids")

    items, prefabs, kits = ig["items"], ig.get("prefabs", {}), ig["paint_kits"]

    def tr(tag, fallback):
        if tag and tag.startswith("#"):
            return tokens.get(tag[1:].lower(), fallback)
        return fallback

    kit_by_name = {}
    for pid, pk in kits.items():
        name = pk.get("name", "")
        if pid == "0" or name in ("default", "workshop_default"):
            continue
        shown = (tr(pk.get("description_tag"), None) or tr(f"#PaintKit_{name}_Tag", None)
                 or tr(f"#PaintKit_{name}", None) or name)
        kit_by_name[name] = (int(pid), shown)
    unresolved = sum(1 for _, (pid, shown) in kit_by_name.items() if looks_internal(shown))
    if kit_by_name and unresolved > len(kit_by_name) * 0.2:
        print(f"[catalog] WARNING: {unresolved}/{len(kit_by_name)} paint kits kept internal names")

    agent_base = {
        "fbi": "FBI", "gign": "GIGN", "gsg9": "GSG-9", "idf": "IDF", "sas": "SAS",
        "seal_team6": "SEAL Team 6", "swat": "SWAT", "heavy": "Тяжёлый",
        "anarchist": "Анархист", "balkan": "Балканец", "leet": "Elite Crew",
        "phoenix": "Феникс", "pirate": "Пират", "professional": "Профессионал",
        "separatist": "Сепаратист",
    }

    def agent_label(internal):
        n = str(internal).replace("customplayer_", "")
        for pref in ("ctm_", "tm_"):
            if n.startswith(pref):
                n = n[len(pref):]
                break
        variant = ""
        if "_variant" in n:
            base, var = n.rsplit("_variant", 1)
            if len(var) == 1 and var.isalpha():
                n, variant = base, " " + var.upper()
        return (agent_base.get(n) or n.replace("_", " ").title()) + variant

    agents, seen_agents = [], set()
    for did, it in items.items():
        if not did.isdigit() or not isinstance(it, dict):
            continue
        slot = pget(it, "item_slot", prefabs)
        model = pget(it, "model_player", prefabs) or ""
        if slot != "customplayer" or not model.startswith("models/player/custom_player/"):
            continue
        if model in seen_agents:
            continue
        seen_agents.add(model)
        internal = it.get("name", did)
        shown = tr(pget(it, "item_name", prefabs), None)
        if not shown or looks_internal(shown):
            shown = agent_label(internal)
        classes = it.get("used_by_classes", {}) if isinstance(it.get("used_by_classes"), dict) else {}
        team = "T" if "terrorists" in classes else ("CT" if "counter-terrorists" in classes else "")
        if team:
            shown = f"{shown} ({team})"
        stem = Path(model).stem
        icon = "econ/characters/customplayer_" + stem
        agents.append({"defidx": int(did), "name": shown, "model": model, "team": team,
                       "icon": icon, "skins": []})
    agents.sort(key=lambda a: (a["team"], a["name"].lower()))

    sticker_kits = []
    for sid, sk in (ig.get("sticker_kits") or {}).items():
        if not str(sid).isdigit() or not isinstance(sk, dict) or not sk.get("sticker_material"):
            continue
        label = tr(sk.get("description_tag"), None) or tr(f"#StickerKit_{sk.get('name','')}", None) \
            or sk.get("name") or str(sid)
        if looks_internal(label):
            label = str(sk.get("name") or sid).replace("_", " ")
        sticker_kits.append({"id": int(sid), "name": label})
    sticker_kits.sort(key=lambda s: s["id"])

    known = {}
    for did, it in items.items():
        if not did.isdigit() or not isinstance(it, dict):
            continue
        name = it.get("name", "")
        cat = None
        if name == "weapon_bayonet" or name.startswith("weapon_knife"):
            cat = "Ножи"
        elif ("gloves" in name or "handwraps" in name) and not name.startswith("weapon_"):
            cat = "Перчатки"
        elif name.startswith("weapon_"):
            short = name[len("weapon_"):]
            for c, lst in CATEGORIES.items():
                if short in lst:
                    cat = c
        if not cat:
            continue
        disp = tr(pget(it, "item_name", prefabs), name)
        known[name] = {"defidx": int(did), "name": disp, "cat": cat,
                       "model": pget(it, "model_player", prefabs), "skins": []}

    def add_skin(wn, pid, disp, icon=None):
        for s in known[wn]["skins"]:
            if s["paint"] == pid:
                if icon and "icon" not in s:
                    s["icon"] = icon
                return
        entry = {"paint": pid, "name": disp}
        if icon:
            entry["icon"] = icon
        known[wn]["skins"].append(entry)

    by_len = sorted(known, key=len, reverse=True)
    icons = ig["alternate_icons2"].get("weapon_icons", {})
    for ic in icons.values():
        path = ic.get("icon_path", "") if isinstance(ic, dict) else ""
        base = path.split("/")[-1]
        if not base.endswith("_light"):
            continue
        base = base[:-6]
        for wn in by_len:
            if base.startswith(wn + "_") and base[len(wn) + 1:] in kit_by_name:
                pid, disp = kit_by_name[base[len(wn) + 1:]]
                add_skin(wn, pid, disp, path)
                break

    for st in ig.get("item_sets", {}).values():
        for key in (st.get("items", {}) if isinstance(st, dict) else {}):
            if key.startswith("[") and "]" in key:
                kit, wn = key[1:].split("]", 1)
                if kit in kit_by_name and wn in known:
                    add_skin(wn, *kit_by_name[kit])

    if not any(w["skins"] for w in known.values()):
        raise CatalogError(
            f"no skins found (items={len(items)}, weapons matched={len(known)}, "
            f"paint kits={len(kit_by_name)}, icons={len(icons)}).")

    cats = {c: [] for c in ORDER}
    for wn, w in known.items():
        if not w["skins"] and w["cat"] != "Ножи":
            continue
        w["skins"].sort(key=lambda s: s["name"].lower())
        cats[w["cat"]].append({"defidx": w["defidx"], "name": w["name"],
                               "model": w["model"], "skins": w["skins"]})
    for c in cats:
        cats[c].sort(key=lambda w: w["name"].lower())

    cats["Агенты"] = agents
    out = {"knife_ids": sorted(w["defidx"] for w in cats["Ножи"]),
           "sticker_kits": sticker_kits, "categories": cats}
    return out


def write_catalog(out, path) -> str:
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    cats = out["categories"]
    total = sum(len(w["skins"]) for c in cats.values() for w in c)
    return f"catalog written: {path} ({sum(len(v) for v in cats.values())} items, {total} skins)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csgo")
    ap.add_argument("--items-game")
    ap.add_argument("--lang")
    ap.add_argument("--out", default="catalog.json")
    a = ap.parse_args()
    try:
        print(write_catalog(build_catalog(a.csgo, a.items_game, a.lang), a.out))
    except CatalogError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()