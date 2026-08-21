"""Harness: D1 travel accumulator and logger wiring (imports REAL modules).

Part 1 imports the REAL core.cell.arms (isaaclab and torch stubbed with
numpy, the established pattern) and drives the REAL Cell.tick with fake
arms whose end effectors move a scripted path. Expected travel is computed
by hand and compared.

Part 2 imports the REAL instrumentation.episode_logger and calls finish()
with a fake coordinator: once WITH cell.arms carrying travel_m (values must
appear per arm plus a metrics rollup) and once WITHOUT a cell attribute
(getattr guard: nothing breaks, no travel keys).

Run: python3 h_travel_d1.py
"""
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

# ---- stubs so core.cell.arms imports without Isaac or torch --------------


class _T(np.ndarray):
    def clone(self):
        return self.copy().view(_T)


def _tensor(x, **kw):
    return np.asarray(x, dtype=float).view(_T)


torch_stub = types.ModuleType("torch")
torch_stub.tensor = _tensor
torch_stub.norm = lambda x: float(np.linalg.norm(np.asarray(x)))
torch_stub.float32 = np.float32
sys.modules.setdefault("torch", torch_stub)

for name in ("isaaclab", "isaaclab.controllers", "isaaclab.managers",
             "isaaclab.utils", "isaaclab.utils.math"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["isaaclab.controllers"].DifferentialIKController = object
sys.modules["isaaclab.controllers"].DifferentialIKControllerCfg = object
sys.modules["isaaclab.managers"].SceneEntityCfg = object
for fn in ("matrix_from_quat", "quat_inv", "subtract_frame_transforms"):
    setattr(sys.modules["isaaclab.utils.math"], fn, lambda *a, **k: None)

from core.cell import arms as arms_mod          # REAL module

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


# ---- part 1: real Cell.tick over scripted fake arms -----------------------

class FakeArm:
    def __init__(self, path):
        self.path = path                  # list of (x, y, z) per tick
        self.i = -1
        self.travel_m = 0.0
        self._last_ee_w = None
        self._goal = None

    def step(self):
        self.i = min(self.i + 1, len(self.path) - 1)
        return None

    def update_carried(self):
        pass

    def ee_pos_w(self):
        return _tensor([list(self.path[self.i])])


class FakeSim:
    def get_physics_dt(self):
        return 0.01

    def step(self, render=True):
        pass


class FakeScene:
    def write_data_to_sim(self):
        pass

    def update(self, dt):
        pass


path_a = [(0.0, 0.0, 0.5), (0.1, 0.0, 0.5), (0.2, 0.0, 0.5),
          (0.2, 0.3, 0.5), (0.2, 0.3, 0.5)]          # 0.1+0.1+0.3+0 = 0.5
path_b = [(1.0, 1.0, 0.5)] * 5                       # parked: 0.0

fa, fb = FakeArm(path_a), FakeArm(path_b)
cell = arms_mod.Cell(FakeSim(), FakeScene(), {"a": fa, "b": fb})
for _ in range(5):
    cell.tick(render=False)

check("moving arm accumulates path length",
      abs(fa.travel_m - 0.5) < 1e-9, f"travel_m={fa.travel_m}")
check("parked arm accumulates zero",
      fb.travel_m == 0.0, f"travel_m={fb.travel_m}")
check("first tick sets baseline, adds nothing",
      fa._last_ee_w is not None)

# ---- part 2: real episode logger picks travel up, guarded -----------------

from instrumentation.episode_logger import EpisodeLogger   # REAL module


class NS(types.SimpleNamespace):
    pass


def fake_coord(with_cell):
    m = NS(makespan_ticks=100, requeued=0,
           completed={"a": 2}, blocked={"a": 3, "b": 1})
    locks = NS(ledger=[])
    agents = {"a": None, "b": None}
    c = NS(m=m, locks=locks, agents=agents, pool=[])
    if with_cell:
        c.cell = NS(arms={"a": NS(travel_m=0.5), "b": NS(travel_m=0.0)})
    return c


out = "/tmp/h_d1_out"
log = EpisodeLogger(out_dir=out, test="d1")
data_with = None
path = log.finish(fake_coord(True), filename="with_cell.json")
import json
with open(os.path.join(out, "with_cell.json")) as f:
    data_with = json.load(f)
log2 = EpisodeLogger(out_dir=out, test="d1")
log2.finish(fake_coord(False), filename="no_cell.json")
with open(os.path.join(out, "no_cell.json")) as f:
    data_without = json.load(f)

pa = data_with["per_arm"]
check("per_arm travel_m recorded",
      pa.get("a", {}).get("travel_m") == 0.5 and
      pa.get("b", {}).get("travel_m") == 0.0, str(pa))
check("metrics travel_m_total rollup",
      data_with["metrics"].get("travel_m_total") == 0.5)
check("old counters untouched",
      pa["a"]["completed_legs"] == 2 and pa["a"]["blocked_ticks"] == 3)
pa2 = data_without["per_arm"]
check("no cell attr: finish() still writes, no travel keys",
      all("travel_m" not in v for v in pa2.values()) and
      "travel_m_total" not in data_without["metrics"])
check("agents-only arm still listed in per_arm", "b" in pa and "b" in pa2)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
