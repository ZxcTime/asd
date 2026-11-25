import json
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

# ---------- инжектор (вшит) ----------
import ctypes
import subprocess

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_READWRITE = 0x04


def find_pid(name: str) -> int:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return 0
    if not out or out.startswith("INFO:"):
        return 0
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            try:
                return int(parts[1])
            except ValueError:
                pass
    return 0


def inject_dll(pid: int, dll_path: str) -> bool:
    dll_path = os.path.abspath(dll_path)
    if not os.path.isfile(dll_path):
        return False
    h_proc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_proc:
        return False
    try:
        data = dll_path.encode("ascii") + b"\x00"
        addr = kernel32.VirtualAllocEx(h_proc, None, len(data),
                                       MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not addr:
            return False
        written = ctypes.c_size_t(0)
        if not kernel32.WriteProcessMemory(h_proc, addr, data, len(data),
                                           ctypes.byref(written)):
            return False
        k32 = kernel32.GetModuleHandleW("kernel32.dll")
        load_lib = kernel32.GetProcAddress(k32, b"LoadLibraryA")
        if not load_lib:
            return False
        thread = kernel32.CreateRemoteThread(h_proc, None, 0, load_lib, addr, 0, None)
        if not thread:
            return False
        kernel32.WaitForSingleObject(thread, 5000)
        code = ctypes.c_ulong(0)
        kernel32.GetExitCodeThread(thread, ctypes.byref(code))
        kernel32.CloseHandle(thread)
        kernel32.VirtualFreeEx(h_proc, addr, 0, 0x8000)
        return code.value != 0
    finally:
        kernel32.CloseHandle(h_proc)


def inject_into(process_name: str, dll_name: str) -> bool:
    pid = find_pid(process_name)
    if not pid:
        return False
    return inject_dll(pid, dll_name)


# ---------- конфиги ----------
CONFIG = "csgo_skins.json"
CATALOG = "catalog.json"
SYNC = "sync.json"
DLL = "csgo_skins.dll"

ORDER = ["Винтовки", "Пистолеты", "ПП", "Снайперские", "Тяжёлые", "Ножи", "Перчатки", "Агенты"]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("cs2 skin changer")
        self.geometry("860x660")

        self.cfg = load_json(CONFIG, {
            "account_id": 0, "enabled": False,
            "skins": {}, "knife": {}, "gloves": {}, "agents": {}, "sync": {},
        })
        self.cat = load_json(CATALOG, None)

        if not self.cat:
            messagebox.showerror(
                "catalog",
                "catalog.json не найден.\n"
                "Сначала собери каталог:\n"
                "python build_catalog.py --csgo \".../game/csgo\"",
            )
            self.destroy()
            return

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._tab_weapons(nb)
        self._tab_knife(nb)
        self._tab_gloves(nb)
        self._tab_agents(nb)
        self._tab_sync(nb)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Сохранить всё", command=self.save_all).pack(side="left")
        ttk.Button(bar, text="Инжект в CS2", command=self.do_inject).pack(side="left", padx=6)

        self.en_var = tk.BooleanVar(value=self.cfg.get("enabled", False))
        ttk.Checkbutton(bar, text="enabled", variable=self.en_var,
                        command=self.toggle).pack(side="right")

        # авто-инжект, если CS2 уже запущена
        self.after(600, self._auto_inject)

    # ---------- inject ----------
    def _auto_inject(self):
        if find_pid("cs2.exe") and not messagebox.askyesno(
                "inject", "CS2 уже запущена. Заинжектить DLL автоматически?"):
            return
        if find_pid("cs2.exe"):
            self.do_inject()

    def do_inject(self):
        if not os.path.isfile(DLL):
            messagebox.showerror("inject", f"{DLL} не найден.\nЗапусти build.bat.")
            return
        if not find_pid("cs2.exe"):
            messagebox.showerror("inject", "cs2.exe не запущен.\nЗапусти CS2 и попробуй снова.")
            return
        if inject_into("cs2.exe", DLL):
            messagebox.showinfo("inject", "DLL в cs2.exe. В игре нажми INSERT.")
        else:
            messagebox.showerror(
                "inject",
                "Не удалось инжектнуть. Проверь:\n"
                "• CS2 запущена\n"
                "• csgo_skins.dll рядом с gui.py\n"
                "• Python x64\n"
                "• CS2 запущена с -insecure или в VM\n"
                "• антивирус не блокирует",
            )

    # ---------- weapons ----------
    def _tab_weapons(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Оружие")
        left = ttk.Frame(f)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Категория").pack(anchor="w")
        cats = [c for c in ORDER if c in self.cat["categories"]
                and c not in ("Ножи", "Перчатки", "Агенты")]
        self.cat_var = tk.StringVar(value=cats[0] if cats else "")
        cb = ttk.Combobox(left, values=cats, textvariable=self.cat_var,
                          state="readonly", width=22)
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_weapons())

        ttk.Label(left, text="Оружие").pack(anchor="w", pady=(8, 0))
        self.wl = tk.Listbox(left, width=32, height=22, exportselection=False)
        self.wl.pack(fill="y", expand=True)
        self.wl.bind("<<ListboxSelect>>", lambda e: self._fill_skins())

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True, padx=8)
        ttk.Label(right, text="Скин").pack(anchor="w")
        self.sl = tk.Listbox(right, height=22, exportselection=False)
        self.sl.pack(fill="both", expand=True)

        btm = ttk.Frame(f)
        btm.pack(fill="x", pady=6)
        ttk.Label(btm, text="wear").pack(side="left")
        self.wear_v = tk.StringVar(value="0.0001")
        ttk.Entry(btm, textvariable=self.wear_v, width=8).pack(side="left", padx=4)
        ttk.Label(btm, text="seed").pack(side="left")
        self.seed_v = tk.StringVar(value="0")
        ttk.Entry(btm, textvariable=self.seed_v, width=6).pack(side="left", padx=4)
        ttk.Button(btm, text="Применить к оружию",
                   command=self.apply_weapon).pack(side="right")

        self._wcache = {}
        self._fill_weapons()

    def _fill_weapons(self):
        self.wl.delete(0, tk.END)
        self._wcache.clear()
        for w in self.cat["categories"].get(self.cat_var.get(), []):
            self._wcache[len(self._wcache)] = w
            self.wl.insert(tk.END, w["name"])
        if self.wl.size():
            self.wl.selection_set(0)
            self._fill_skins()

    def _fill_skins(self):
        self.sl.delete(0, tk.END)
        sel = self.wl.curselection()
        if not sel:
            return
        w = self._wcache[sel[0]]
        cur = self.cfg.get("skins", {}).get(str(w["defidx"]), {}).get("paint_kit")
        for i, s in enumerate(w.get("skins", [])):
            self.sl.insert(tk.END, s["name"])
            if s["paint"] == cur:
                self.sl.selection_set(i)
                self.sl.see(i)

    def apply_weapon(self):
        ws = self.wl.curselection()
        ss = self.sl.curselection()
        if not ws or not ss:
            return
        w = self._wcache[ws[0]]
        s = w["skins"][ss[0]]
        try:
            wear = float(self.wear_v.get() or 0.0001)
            seed = int(self.seed_v.get() or 0)
        except ValueError:
            messagebox.showerror("wear/seed", "wear — число 0.0–1.0, seed — целое")
            return
        self.cfg.setdefault("skins", {})[str(w["defidx"])] = {
            "paint_kit": s["paint"],
            "wear": wear, "seed": seed,
            "stattrak": -1, "stickers": [0, 0, 0, 0, 0],
        }
        save_json(CONFIG, self.cfg)
        messagebox.showinfo("ok", f"{w['name']} → {s['name']}")

    # ---------- knife ----------
    def _tab_knife(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Нож")
        knives = self.cat["categories"].get("Ножи", [])
        self._knives = knives
        names = [k["name"] for k in knives]
        self.kvar = tk.StringVar()
        ttk.Label(f, text="Нож").pack(anchor="w")
        kc = ttk.Combobox(f, values=names, textvariable=self.kvar,
                          state="readonly", width=40)
        kc.pack(fill="x")
        kc.bind("<<ComboboxSelected>>", lambda e: self._fill_knife_skins())
        ttk.Label(f, text="Скин").pack(anchor="w", pady=(8, 0))
        self.ksl = tk.Listbox(f, height=20, exportselection=False)
        self.ksl.pack(fill="both", expand=True)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=6)
        ttk.Label(bar, text="wear").pack(side="left")
        self.kwear = tk.StringVar(value="0.0001")
        ttk.Entry(bar, textvariable=self.kwear, width=8).pack(side="left", padx=4)
        ttk.Button(bar, text="Применить нож",
                   command=self.apply_knife).pack(side="right")
        if names:
            kc.current(0)
            self._fill_knife_skins()

    def _fill_knife_skins(self):
        self.ksl.delete(0, tk.END)
        for k in self._knives:
            if k["name"] == self.kvar.get():
                for s in k.get("skins", []):
                    self.ksl.insert(tk.END, s["name"])
                return

    def apply_knife(self):
        sel = self.kvar.get()
        ss = self.ksl.curselection()
        if not sel or not ss:
            return
        for k in self._knives:
            if k["name"] == sel:
                s = k["skins"][ss[0]]
                try:
                    wear = float(self.kwear.get() or 0.0001)
                except ValueError:
                    messagebox.showerror("wear", "wear — число 0.0–1.0")
                    return
                self.cfg["knife"] = {
                    "defidx": k["defidx"], "paint_kit": s["paint"],
                    "wear": wear, "seed": 0, "stattrak": -1,
                    "model": k.get("model", ""), "stickers": [0, 0, 0, 0, 0],
                }
                save_json(CONFIG, self.cfg)
                messagebox.showinfo("ok", f"{k['name']} → {s['name']}")
                return

    # ---------- gloves ----------
    def _tab_gloves(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Перчатки")
        gloves = self.cat["categories"].get("Перчатки", [])
        self._gloves = gloves
        names = [g["name"] for g in gloves]
        self.gvar = tk.StringVar()
        ttk.Label(f, text="Перчатки").pack(anchor="w")
        gc = ttk.Combobox(f, values=names, textvariable=self.gvar,
                          state="readonly", width=40)
        gc.pack(fill="x")
        gc.bind("<<ComboboxSelected>>", lambda e: self._fill_glove_skins())
        ttk.Label(f, text="Скин").pack(anchor="w", pady=(8, 0))
        self.gsl = tk.Listbox(f, height=20, exportselection=False)
        self.gsl.pack(fill="both", expand=True)
        ttk.Button(f, text="Применить перчатки",
                   command=self.apply_gloves).pack(pady=6)
        if names:
            gc.current(0)
            self._fill_glove_skins()

    def _fill_glove_skins(self):
        self.gsl.delete(0, tk.END)
        for g in self._gloves:
            if g["name"] == self.gvar.get():
                for s in g.get("skins", []):
                    self.gsl.insert(tk.END, s["name"])
                return

    def apply_gloves(self):
        sel = self.gvar.get()
        ss = self.gsl.curselection()
        if not sel or not ss:
            return
        for g in self._gloves:
            if g["name"] == sel:
                s = g["skins"][ss[0]]
                self.cfg["gloves"] = {
                    "defidx": g["defidx"], "paint_kit": s["paint"],
                    "wear": 0.0001, "seed": 0, "stattrak": -1,
                    "model": g.get("model", ""), "stickers": [0, 0, 0, 0, 0],
                }
                save_json(CONFIG, self.cfg)
                messagebox.showinfo("ok", f"{g['name']} → {s['name']}")
                return

    # ---------- agents ----------
    def _tab_agents(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Агенты")
        self.agent_v = {}
        agents = self.cat["categories"].get("Агенты", [])
        for team in ("T", "CT"):
            ttk.Label(f, text=team).pack(anchor="w", pady=(6, 0))
            names = [a["name"] for a in agents if a.get("team") == team]
            v = tk.StringVar()
            cb = ttk.Combobox(f, values=names, textvariable=v,
                              state="readonly", width=64)
            cb.pack(fill="x")
            self.agent_v[team] = v
            cur = self.cfg.get("agents", {}).get(team, {}).get("name")
            if cur in names:
                cb.current(names.index(cur))
        ttk.Button(f, text="Применить агентов",
                   command=self.apply_agents).pack(pady=8)

    def apply_agents(self):
        agents = self.cat["categories"].get("Агенты", [])
        for team, var in self.agent_v.items():
            for a in agents:
                if a["name"] == var.get() and a.get("team") == team:
                    self.cfg.setdefault("agents", {})[team] = {
                        "defidx": a["defidx"], "model": a["model"],
                        "name": a["name"], "team": team,
                    }
        save_json(CONFIG, self.cfg)
        messagebox.showinfo("ok", "агенты сохранены")

    # ---------- sync ----------
    def _tab_sync(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Синк")
        ttk.Label(f, text="SteamID64 друга").pack(anchor="w")
        self.sync_id = ttk.Entry(f)
        self.sync_id.pack(fill="x")
        ttk.Label(f, text="defidx:paint_kit через запятую (напр. 7:639,16:309)").pack(
            anchor="w", pady=(6, 0))
        self.sync_map = ttk.Entry(f)
        self.sync_map.pack(fill="x")
        ttk.Button(f, text="Добавить в sync.json",
                   command=self.add_sync).pack(pady=8)
        ttk.Label(f, text="Другу нужен этот же DLL + твой sync.json.",
                  foreground="#888").pack(anchor="w", pady=(10, 0))

    def add_sync(self):
        sid = self.sync_id.get().strip()
        pairs = self.sync_map.get().strip()
        if not sid or not pairs:
            return
        sync = load_json(SYNC, {})
        entry = {"skins": {}}
        for p in pairs.split(","):
            d, _, paint = p.partition(":")
            if d.strip().isdigit() and paint.strip().isdigit():
                entry["skins"][d.strip()] = {
                    "paint_kit": int(paint.strip()),
                    "wear": 0.0001, "seed": 0, "stattrak": -1,
                }
        sync[sid] = entry
        save_json(SYNC, sync)
        messagebox.showinfo("sync", f"добавлен {sid}")

    # ---------- common ----------
    def toggle(self):
        self.cfg["enabled"] = self.en_var.get()
        save_json(CONFIG, self.cfg)

    def save_all(self):
        save_json(CONFIG, self.cfg)
        messagebox.showinfo("ok", "csgo_skins.json сохранён")


if __name__ == "__main__":
    App().mainloop()