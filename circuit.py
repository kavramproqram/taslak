"""
Kavram - devre modeli ve dijital simülatör.

Arayüzden bağımsızdır (PyQt5 gerektirmez).
  * Her pin "uid:PIN" anahtarıyla gösterilir.
  * Kablolar ve pinler birlikte "net" (düğüm) oluşturur.
  * Bir net'in değeri, o nete sinyal süren çıkışlara bakılarak bulunur.
  * Bir net'e hem 0 hem 1 süren çıkış varsa kısa devre sayılır.
"""
from collections import namedtuple
from dataclasses import dataclass, field

Pin = namedtuple("Pin", "id x y dir")  # dir: 'in' veya 'out'

SUPPLY_HIGH = 2.5  # volt; bu değerin üstü 1 (HIGH) kabul edilir


def _gate(name, w, h, pins_in, pins_out):
    return {"name": name, "sub": "", "group": "kapi", "w": w, "h": h, "ins": [p.id for p in pins_in],
            "pins": pins_in + pins_out}


COMPONENTS = {
    # ----- Temel -----
    "vcc": {"name": "Güç Kaynağı", "sub": "Vcc", "group": "temel", "w": 92, "h": 56,
            "pins": [Pin("OUT", 92, 28, "out")]},
    "gnd": {"name": "Toprak", "sub": "GND", "group": "temel", "w": 92, "h": 56,
            "pins": [Pin("OUT", 0, 28, "out")]},
    "switch": {"name": "Anahtar", "sub": "Giriş", "group": "temel", "w": 104, "h": 60,
               "pins": [Pin("IN", 0, 30, "in"), Pin("OUT", 104, 30, "out")]},
    "touch": {"name": "Dokunmatik", "sub": "Giriş", "group": "temel", "w": 124, "h": 88,
              "pins": [Pin("OUT", 124, 44, "out")]},
    "screen": {"name": "Ekran", "sub": "Çıkış", "group": "temel", "w": 124, "h": 88,
               "pins": [Pin("IN", 0, 44, "in")]},
    "led": {"name": "LED", "sub": "Çıkış", "group": "temel", "w": 92, "h": 60,
            "pins": [Pin("IN", 0, 30, "in")]},
    "clock": {"name": "Saat", "sub": "Kristal", "group": "temel", "w": 104, "h": 60,
              "pins": [Pin("OUT", 104, 30, "out")]},
    # ----- Mantık kapıları -----
    "not": {"name": "NOT", "sub": "Değil", "group": "kapi", "w": 104, "h": 60, "ins": ["A"],
            "pins": [Pin("A", 0, 30, "in"), Pin("Y", 104, 30, "out")]},
    "and": _gate("AND", 112, 72, [Pin("A", 0, 24, "in"), Pin("B", 0, 48, "in")], [Pin("Y", 112, 36, "out")]),
    "or": _gate("OR", 112, 72, [Pin("A", 0, 24, "in"), Pin("B", 0, 48, "in")], [Pin("Y", 112, 36, "out")]),
    "nand": _gate("NAND", 112, 72, [Pin("A", 0, 24, "in"), Pin("B", 0, 48, "in")], [Pin("Y", 112, 36, "out")]),
    "nor": _gate("NOR", 112, 72, [Pin("A", 0, 24, "in"), Pin("B", 0, 48, "in")], [Pin("Y", 112, 36, "out")]),
    "xor": _gate("XOR", 112, 72, [Pin("A", 0, 24, "in"), Pin("B", 0, 48, "in")], [Pin("Y", 112, 36, "out")]),
    # ----- İşlemci -----
    "hadder": {"name": "İşlemci Çekirdeği", "sub": "ALU · 1 bit", "group": "islemci", "w": 150, "h": 128,
               "ins": ["A", "B"],
               "pins": [Pin("A", 0, 36, "in"), Pin("B", 0, 92, "in"),
                        Pin("S", 150, 36, "out"), Pin("C", 150, 92, "out")]},
    # ----- Bellek -----
    "dff": {"name": "D Flip-Flop", "sub": "1 bit", "group": "bellek", "w": 112, "h": 76,
            "pins": [Pin("D", 0, 24, "in"), Pin("CLK", 0, 52, "in"), Pin("Q", 112, 38, "out")]},
    "ram": {"name": "RAM", "sub": "1 bit · uçucu", "group": "bellek", "w": 156, "h": 88,
            "pins": [Pin("D", 0, 24, "in"), Pin("WE", 0, 44, "in"), Pin("CLK", 0, 64, "in"),
                     Pin("Q", 156, 44, "out")]},
    "ssd": {"name": "SSD", "sub": "1 bit · kalıcı", "group": "bellek", "w": 156, "h": 88,
            "pins": [Pin("D", 0, 24, "in"), Pin("WE", 0, 44, "in"), Pin("CLK", 0, 64, "in"),
                     Pin("Q", 156, 44, "out")]},
}

# Tek çıkışlı basit kapılar
GATE_FN = {
    "not": lambda a: not a,
    "and": lambda a, b: a and b,
    "or": lambda a, b: a or b,
    "nand": lambda a, b: not (a and b),
    "nor": lambda a, b: not (a or b),
    "xor": lambda a, b: a != b,
}

# Kenarda örneklenen bellek elemanları: tür -> (yazma_etkin_pini)
MEMORY_TYPES = {"dff": None, "ram": "WE", "ssd": "WE"}
VOLATILE = {"dff", "ram"}  # reset ile silinir; ssd kalıcıdır

GROUPS = [
    ("temel", "Temel"),
    ("kapi", "Mantık Kapıları"),
    ("islemci", "İşlemci"),
    ("bellek", "Bellek"),
]

UPCOMING = [
    ("NPN Transistör", "B · C · E"),
    ("PNP Transistör", "B · C · E"),
    ("NMOS Transistör", "G · D · S"),
    ("PMOS Transistör", "G · D · S"),
    ("Direnç", "1 · 2"),
    ("Kapasitör", "+ · -"),
]


def pin_key(uid, pin_id):
    return f"{uid}:{pin_id}"


@dataclass
class Part:
    uid: int
    type: str
    x: int
    y: int
    state: bool = False       # anahtar/dokunma, saat, bellek Q, LED ve ekran durumu
    outs: dict = field(default_factory=dict)  # kombinasyonel çıkışlar: pin_id -> bool
    prev_clk: bool = False


class Circuit:
    def __init__(self):
        self.voltage = 5.0
        self.clear()

    def clear(self):
        self.parts = []
        self.wires = []   # her kablo: {"a": key, "b": key}
        self.next_uid = 1
        self.tick_count = 0

    # ---------- Parça ve kablo ----------
    def add_part(self, type_, x, y):
        p = Part(uid=self.next_uid, type=type_, x=round(x), y=round(y))
        self.next_uid += 1
        self.parts.append(p)
        return p

    def part(self, uid):
        for p in self.parts:
            if p.uid == uid:
                return p
        return None

    def remove_part(self, uid):
        self.parts = [p for p in self.parts if p.uid != uid]
        self.wires = [
            w for w in self.wires
            if int(w["a"].split(":")[0]) != uid and int(w["b"].split(":")[0]) != uid
        ]

    def connect(self, a, b):
        if a == b:
            return False
        for w in self.wires:
            if (w["a"] == a and w["b"] == b) or (w["a"] == b and w["b"] == a):
                return False
        self.wires.append({"a": a, "b": b})
        return True

    def remove_wire(self, index):
        del self.wires[index]

    def pin_def(self, key):
        uid, _, pin_id = key.partition(":")
        part = self.part(int(uid))
        if part is None:
            return None
        for pin in COMPONENTS[part.type]["pins"]:
            if pin.id == pin_id:
                return part, pin
        return None

    def pin_pos(self, key):
        r = self.pin_def(key)
        if r is None:
            return None
        part, pin = r
        return (part.x + pin.x, part.y + pin.y)

    # ---------- Netler ve seviyeler ----------
    def nets(self):
        parent = {}

        def find(k):
            parent.setdefault(k, k)
            r = k
            while parent[r] != r:
                r = parent[r]
            parent[k] = r
            return r

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for p in self.parts:
            for pin in COMPONENTS[p.type]["pins"]:
                find(pin_key(p.uid, pin.id))
        for w in self.wires:
            union(w["a"], w["b"])
        return {k: find(k) for k in list(parent)}

    def out_value(self, p, pin_id):
        """Bir çıkış pininin şu anki değeri."""
        if p.type in ("clock", "dff", "ram", "ssd", "touch"):
            return p.state
        return p.outs.get(pin_id, False)

    def levels(self, net):
        """net kökü -> (değer, kısa_devre_mi)"""
        acc = {}
        for p in self.parts:
            for pin in COMPONENTS[p.type]["pins"]:
                if pin.dir != "out":
                    continue
                root = net[pin_key(p.uid, pin.id)]
                h, l = acc.get(root, (False, False))
                v = bool(self.out_value(p, pin.id))
                acc[root] = (h or v, l or not v)
        return {root: (h, h and l) for root, (h, l) in acc.items()}

    def level_of(self, net, lv, key):
        return lv.get(net.get(key), (False, False))[0]

    def analyze(self):
        net = self.nets()
        lv = self.levels(net)
        conflict = {k for k, root in net.items() if lv.get(root, (False, False))[1]}
        return net, lv, conflict

    # ---------- Simülasyon ----------
    def settle(self):
        """Kombinasyonel mantığı kararlı hale getirir (en fazla 20 tur)."""
        net = self.nets()
        for _ in range(20):
            lv = self.levels(net)
            changed = False
            for p in self.parts:
                new = self._combinational(p, net, lv)
                if new is not None and new != p.outs:
                    p.outs = new
                    changed = True
            if not changed:
                break

        lv = self.levels(net)
        for p in self.parts:
            if p.type in ("led", "screen"):
                p.state = self.level_of(net, lv, pin_key(p.uid, "IN"))

    def _combinational(self, p, net, lv):
        """Bir parçanın çıkış sözlüğünü hesaplar. Çıkışı olmayanlar için None."""
        def lvl(pin_id):
            return self.level_of(net, lv, pin_key(p.uid, pin_id))

        if p.type == "vcc":
            return {"OUT": self.voltage >= SUPPLY_HIGH}
        if p.type == "gnd":
            return {"OUT": False}
        if p.type == "switch":
            return {"OUT": bool(p.state and lvl("IN"))}
        if p.type == "hadder":
            a, b = lvl("A"), lvl("B")
            return {"S": a != b, "C": bool(a and b)}
        if p.type in GATE_FN:
            ins = [lvl(i) for i in COMPONENTS[p.type]["ins"]]
            return {"Y": bool(GATE_FN[p.type](*ins))}
        return None

    def tick(self):
        """Bir saat darbesi: saat değişir, yükselen kenarda bellekler örnekler."""
        self.tick_count += 1
        for p in self.parts:
            if p.type == "clock":
                p.state = not p.state

        net = self.nets()
        lv = self.levels(net)
        for p in self.parts:
            if p.type not in MEMORY_TYPES:
                continue
            clk = self.level_of(net, lv, pin_key(p.uid, "CLK"))
            if clk and not p.prev_clk:
                we_pin = MEMORY_TYPES[p.type]
                writable = we_pin is None or self.level_of(net, lv, pin_key(p.uid, we_pin))
                if writable:
                    p.state = self.level_of(net, lv, pin_key(p.uid, "D"))
            p.prev_clk = clk
        self.settle()

    def reset(self):
        """Sıfırlama: uçucu bellekler ve anahtarlar temizlenir, SSD korunur."""
        self.tick_count = 0
        for p in self.parts:
            if p.type in ("clock", "switch", "touch", "led", "screen") or p.type in VOLATILE:
                p.state = False
            if p.type in MEMORY_TYPES:
                p.prev_clk = False
        self.settle()

    # ---------- Kaydetme ----------
    def to_dict(self):
        return {
            "format": "kavram-devre",
            "version": 3,
            "voltage": self.voltage,
            "parts": [
                {"uid": p.uid, "type": p.type, "x": p.x, "y": p.y, "state": p.state}
                for p in self.parts
            ],
            "wires": [{"a": w["a"], "b": w["b"]} for w in self.wires],
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "kavram-devre":
            raise ValueError("Geçersiz devre dosyası")
        c = cls()
        c.voltage = float(data.get("voltage", 5))
        for p in data.get("parts", []):
            if p.get("type") not in COMPONENTS:
                continue
            uid = int(p["uid"])
            c.parts.append(Part(uid=uid, type=p["type"], x=int(p["x"]), y=int(p["y"]),
                                state=bool(p.get("state", False))))
            c.next_uid = max(c.next_uid, uid + 1)
        wires = [{"a": w["a"], "b": w["b"]} for w in data.get("wires", [])]
        c.wires = [w for w in wires if c.pin_def(w["a"]) and c.pin_def(w["b"])]
        c.settle()
        return c


# ---------- Hazır örnek devreler ----------
def _preset_led(c):
    v = c.add_part("vcc", 40, 120)
    s = c.add_part("switch", 200, 120)
    l = c.add_part("led", 400, 120)
    c.connect(pin_key(v.uid, "OUT"), pin_key(s.uid, "IN"))
    c.connect(pin_key(s.uid, "OUT"), pin_key(l.uid, "IN"))


def _preset_half_adder(c):
    v = c.add_part("vcc", 40, 40)
    a = c.add_part("switch", 200, 40)
    b = c.add_part("switch", 200, 200)
    cpu = c.add_part("hadder", 420, 80)
    s = c.add_part("led", 680, 60)
    k = c.add_part("led", 680, 200)
    c.connect(pin_key(v.uid, "OUT"), pin_key(a.uid, "IN"))
    c.connect(pin_key(v.uid, "OUT"), pin_key(b.uid, "IN"))
    c.connect(pin_key(a.uid, "OUT"), pin_key(cpu.uid, "A"))
    c.connect(pin_key(b.uid, "OUT"), pin_key(cpu.uid, "B"))
    c.connect(pin_key(cpu.uid, "S"), pin_key(s.uid, "IN"))
    c.connect(pin_key(cpu.uid, "C"), pin_key(k.uid, "IN"))


def _preset_dff(c):
    v = c.add_part("vcc", 40, 60)
    s = c.add_part("switch", 200, 60)
    clk = c.add_part("clock", 40, 220)
    f = c.add_part("dff", 400, 120)
    l = c.add_part("led", 640, 140)
    c.connect(pin_key(v.uid, "OUT"), pin_key(s.uid, "IN"))
    c.connect(pin_key(s.uid, "OUT"), pin_key(f.uid, "D"))
    c.connect(pin_key(clk.uid, "OUT"), pin_key(f.uid, "CLK"))
    c.connect(pin_key(f.uid, "Q"), pin_key(l.uid, "IN"))


def _preset_ram_ssd(c):
    v = c.add_part("vcc", 40, 40)
    sd = c.add_part("switch", 220, 40)
    we = c.add_part("switch", 220, 170)
    clk = c.add_part("clock", 40, 280)
    ram = c.add_part("ram", 470, 40)
    ssd = c.add_part("ssd", 470, 230)
    lr = c.add_part("led", 740, 60)
    ls = c.add_part("led", 740, 250)
    c.connect(pin_key(v.uid, "OUT"), pin_key(sd.uid, "IN"))
    c.connect(pin_key(v.uid, "OUT"), pin_key(we.uid, "IN"))
    c.connect(pin_key(sd.uid, "OUT"), pin_key(ram.uid, "D"))
    c.connect(pin_key(sd.uid, "OUT"), pin_key(ssd.uid, "D"))
    c.connect(pin_key(we.uid, "OUT"), pin_key(ram.uid, "WE"))
    c.connect(pin_key(we.uid, "OUT"), pin_key(ssd.uid, "WE"))
    c.connect(pin_key(clk.uid, "OUT"), pin_key(ram.uid, "CLK"))
    c.connect(pin_key(clk.uid, "OUT"), pin_key(ssd.uid, "CLK"))
    c.connect(pin_key(ram.uid, "Q"), pin_key(lr.uid, "IN"))
    c.connect(pin_key(ssd.uid, "Q"), pin_key(ls.uid, "IN"))


PRESETS = [
    {"name": "Basit LED", "desc": "Güç → anahtar → LED", "build": _preset_led},
    {"name": "Yarım Toplayıcı", "desc": "İşlemci çekirdeğiyle iki bit toplama", "build": _preset_half_adder},
    {"name": "1 Bit Bellek", "desc": "D flip-flop ile bir bit saklama", "build": _preset_dff},
    {"name": "RAM ve SSD", "desc": "Sıfırlayınca RAM silinir, SSD kalır", "build": _preset_ram_ssd},
]


def build_preset(index):
    c = Circuit()
    PRESETS[index]["build"](c)
    c.settle()
    return c
