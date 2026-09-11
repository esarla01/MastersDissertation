"""Harness: CLI column names and auto out-name (imports REAL cli_names).

Checks against ycb/cli_names.py as shipped:
  1. Canonical mappings: b1->rule, b2->opt, vlm1->(vlm, A), vlm2->(vlm, V).
  2. Legacy aliases: oracle->b1, opt->b2.
  3. Bare "vlm" and unknown names raise ValueError with guidance.
  4. unique_out_name: <alloc>_<YYYYMMDD>_<HHMMSS> from an injected clock,
     prefixes the allocator, and counter-suffixes on collision with an
     existing .json OR .mp4.
Run: python3 h_cli_names.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                "..", "fourarm", "ycb"))

import cli_names as cn   # REAL module

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


# 1 + 2: mappings and aliases
cases = {
    "b1":     ("b1", "rule", None),
    "b2":     ("b2", "opt", None),
    "vlm1":   ("vlm1", "vlm", "A"),
    "vlm2":   ("vlm2", "vlm", "V"),
    "oracle": ("b1", "rule", None),
    "opt":    ("b2", "opt", None),
}
for name, want in cases.items():
    got = cn.normalize_allocator(name)
    check(f"normalize {name!r}", got == want, f"{got}")

# SUPERSET, not equality. The seven below must all be present and must
# keep their meaning; extra columns added locally (bvlm1, bvlm2 and so on)
# are the user's business and must not fail the suite. Equality here meant
# adding a personal column turned the whole harness red for no defect.
_REQUIRED = {"random", "b1", "b2", "vlm1", "vlm2", "oracle", "opt"}
_missing = _REQUIRED - set(cn.CLI_CHOICES)
check("CLI_CHOICES covers canonical + aliases", not _missing,
      f"missing {sorted(_missing)}; present {sorted(cn.CLI_CHOICES)}")
_extra = sorted(set(cn.CLI_CHOICES) - _REQUIRED)
if _extra:
    print(f"     note: extra local columns present: {_extra}")
check("random column normalizes to the random kind",
      cn.normalize_allocator("random") == ("random", "random", None),
      str(cn.normalize_allocator("random")))

# 3: rejections
for bad in ("vlm", "b3", "hungarian", ""):
    try:
        cn.normalize_allocator(bad)
        check(f"{bad!r} rejected", False, "no exception")
    except ValueError as e:
        detail_ok = (bad != "vlm") or ("vlm1" in str(e) and "vlm2" in str(e))
        check(f"{bad!r} rejected", detail_ok, str(e)[:60])

# 4: auto naming with a fixed clock and collisions
fixed = time.struct_time((2026, 7, 25, 15, 30, 12, 5, 206, 1))
with tempfile.TemporaryDirectory() as d:
    n1 = cn.unique_out_name("vlm2", out_dir=d, clock=lambda: fixed)
    check("stem format <alloc>_<date>_<time>",
          n1 == "vlm2_20260725_153012", n1)
    open(os.path.join(d, n1 + ".json"), "w").close()
    n2 = cn.unique_out_name("vlm2", out_dir=d, clock=lambda: fixed)
    check("collision with .json gets _2", n2 == "vlm2_20260725_153012_2", n2)
    open(os.path.join(d, n2 + ".mp4"), "w").close()
    n3 = cn.unique_out_name("vlm2", out_dir=d, clock=lambda: fixed)
    check("collision with .mp4 also advances",
          n3 == "vlm2_20260725_153012_3", n3)
    nb = cn.unique_out_name("b1", out_dir=d, clock=lambda: fixed)
    check("different allocator, no collision",
          nb == "b1_20260725_153012", nb)
    check("stem starts with the allocator name",
          all(x.split("_")[0] in ("vlm2", "b1")
              for x in (n1, n2, n3, nb)))

print()
# ---------------------------------------------------------------------------
# 5. runner flags exist and reference the right namespace
# ---------------------------------------------------------------------------
# The settle-wait flags parsed correctly but the code that read them said
# args.settle_wait while the runner parses into args_cli, so the episode
# died with a NameError after Isaac had started. The flags are read out of
# the source with ast rather than by importing the runner, which needs
# Isaac. Two separate failures are covered: a flag that never reaches the
# parser, and a reference to a namespace that does not exist.
import ast as _ast

_runner = os.path.join(os.path.dirname(__file__), "..", "fourarm", "ycb",
                       "run_ycb_sort.py")
_tree = _ast.parse(open(_runner).read())
_flags = [n.args[0].value for n in _ast.walk(_tree)
          if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
          and n.func.attr == "add_argument"
          and n.args and isinstance(n.args[0], _ast.Constant)]
check("the runner defines --settle-wait and --settle-phases",
      "--settle-wait" in _flags and "--settle-phases" in _flags,
      str([f for f in _flags if "settle" in str(f)]))

_names = {n.id for n in _ast.walk(_tree) if isinstance(n, _ast.Name)}
check("the runner parses into args_cli and references no bare 'args'",
      "args_cli" in _names and "args" not in _names,
      "a stray 'args' is a NameError only reachable at run time, after "
      "Isaac has already started")

# ---------------------------------------------------------------------------
# 6. every "from X import Y" in the Isaac entry points actually resolves
# ---------------------------------------------------------------------------
# capture_ex2_scene.py imported add_pad_markers from ycb_scene, where it
# does not live, and apply_physics_schemas likewise. Both only fail once
# Isaac has launched, which costs a session per typo. Checked with ast so
# no Isaac import is needed here.
_MODS = {
    "core.cell.scene_cfg": "core/cell/scene_cfg.py",
    "core.cell.zones": "core/cell/zones.py",
    "core.control.tasks": "core/control/tasks.py",
    "core.control.disruptions": "core/control/disruptions.py",
    "core.cell.arms": "core/cell/arms.py",
    "core.decision.state_builder": "core/decision/state_builder.py",
    "core.decision.vlm_allocator": "core/decision/vlm_allocator.py",
    "ycb_scene": "ycb/ycb_scene.py",
    "ycb_objects": "ycb/ycb_objects.py",
    "layouts": "ycb/layouts.py",
    "cli_names": "ycb/cli_names.py",
}
_FA = os.path.join(os.path.dirname(__file__), "..", "fourarm")


def _exported(path):
    out = set()
    for n in _ast.parse(open(path).read()).body:
        if isinstance(n, (_ast.FunctionDef, _ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, _ast.Assign):
            out |= {t.id for t in n.targets if isinstance(t, _ast.Name)}
        elif isinstance(n, (_ast.Import, _ast.ImportFrom)):
            out |= {a.asname or a.name.split(".")[0] for a in n.names}
    return out


_bad = []
for entry in ("ycb/run_ycb_sort.py", "ycb/capture_ex2_scene.py",
              "ycb/run_ycb_probe.py"):
    ep = os.path.join(_FA, entry)
    if not os.path.exists(ep):
        continue
    for node in _ast.walk(_ast.parse(open(ep).read())):
        if isinstance(node, _ast.ImportFrom) and node.module in _MODS:
            have = _exported(os.path.join(_FA, _MODS[node.module]))
            _bad += [(entry, node.module, a.name) for a in node.names
                     if a.name not in have]
check("every project import in the Isaac entry points resolves",
      not _bad, str(_bad[:3]))

# ---------------------------------------------------------------------------
# 7. the EX2 visibility measurement
# ---------------------------------------------------------------------------
# The overhead camera occludes objects under arm links at their home poses.
# p10_A captured the mustard COMPLETELY hidden under ur_w and still wrote a
# record, so the pair differed in visible-versus-invisible rather than in
# pose. The capture tool now measures visibility by differencing the frame
# before and after the object is placed, and refuses below a threshold.
_cap = os.path.join(os.path.dirname(__file__), "..", "fourarm", "ycb",
                    "capture_ex2_scene.py")
_src = open(_cap).read()
check("the capture tool measures visibility and can refuse a capture",
      "visible_fraction" in _src and "SKIP" in _src)
check("refusal happens BEFORE the record is written",
      _src.index("SKIP") < _src.index('with open(trail, "a")'),
      "otherwise an occluded scene lands in the trail anyway")

# The image scale must come from the camera config, not a constant. Checked
# against the geometry: a 32 mm lens with a 20.955 mm aperture 4.25 m above
# the table spans 2.783 m across 1024 px, so a 2.8 m table just fills the
# frame, which is what the captured images show.
_span = (20.955 / 32.0) * (5.0 - 0.75)
check("the derived image scale matches the captured frames",
      abs(1024 / _span - 367.9) < 1.0, f"{1024 / _span:.1f} px/m")
check("the scale is derived from the camera cfg, not hardcoded",
      "horizontal_aperture" in _src and "focal_length" in _src)

# ---------------------------------------------------------------------------
# 8. every Isaac entry point must let AppLauncher register its own args
# ---------------------------------------------------------------------------
# capture_ex2_scene.py declared --headless by hand and never called
# AppLauncher.add_app_launcher_args, so the launcher was unconfigured: the
# app started but close() did not end the process, and every capture had to
# be interrupted by hand. A loop of them hung outright. Checked with ast,
# no Isaac needed.
for _entry in ("ycb/run_ycb_sort.py", "ycb/capture_ex2_scene.py",
               "ycb/run_ycb_probe.py"):
    _p = os.path.join(_FA, _entry)
    if not os.path.exists(_p):
        continue
    _txt = open(_p).read()
    if "AppLauncher" not in _txt:
        continue
    check(f"{_entry} registers AppLauncher's own arguments",
          "add_app_launcher_args" in _txt,
          "without it --headless is parsed but never reaches the launcher")
    check(f"{_entry} does not declare --headless itself",
          '"--headless"' not in _txt,
          "AppLauncher owns that flag; declaring it shadows the real one")
    check(f"{_entry} closes the app", ".close()" in _txt)

# ---------------------------------------------------------------------------
# 9. the visibility baseline must be taken with the cell at rest
# ---------------------------------------------------------------------------
# The first version took the baseline frame after a fixed short hold. The
# arms were still settling, so the empty-to-object difference was mostly
# arm pixels: a constant ~15,500 changed pixels whatever the object's size,
# giving fractions of 6 and 19 where 1 is the maximum possible.
_capsrc = open(os.path.join(_FA, "ycb", "capture_ex2_scene.py")).read()
check("the baseline waits for two successive frames to agree",
      "settle_until_still" in _capsrc and "moved < tol" in _capsrc,
      "a fixed hold is not evidence the cell has stopped moving")
check("a fraction above 1 is refused rather than recorded",
      "suspect" in _capsrc and "frac > 1.5" in _capsrc,
      "the camera cannot see more of an object than the object has")

# ---------------------------------------------------------------------------
# 10. the EX2 capture tool runs a whole set in ONE Isaac session and exits
# ---------------------------------------------------------------------------
# Capturing one scene per process cost 20 s of startup each and, because
# Isaac leaves non-daemon threads behind, needed a manual interrupt each
# time. A 36-scene run meant 36 Ctrl-Cs.
_capsrc = open(os.path.join(_FA, "ycb", "capture_ex2_scene.py")).read()
check("the capture tool builds the scene exactly once",
      _capsrc.count("InteractiveScene(cfg)") == 1,
      "one session for the whole spec, not one per scene")
check("the capture tool forces process exit after closing the app",
      "os._exit(0)" in _capsrc,
      "close() alone leaves Isaac threads running and the process hangs")
check("the capture tool takes a scene SPEC rather than a single scene",
      '"--spec"' in _capsrc and "read_spec" in _capsrc)
check("a malformed spec line is refused by line number, not skipped",
      "line {n}" in _capsrc,
      "a silently dropped scene is a missing pair nobody notices")

# ---------------------------------------------------------------------------
# The scene spec. Points at ex2_block.txt, the spec the reported Experiment 2
# actually ran: 34 positions, matching section 5.3.1.4. It used to point at
# ex2_scenes.txt and assert nine pairs -- that file is the retired mustard
# pilot, it holds eight, only six were ever captured, and no ninth has existed
# in any commit. A gate pinned to a retired file checks nothing.
# ---------------------------------------------------------------------------

_spec = os.path.join(_FA, "ycb", "ex2_block.txt")
if os.path.exists(_spec):
    _rows = [l.split() for l in open(_spec)
             if l.split("#", 1)[0].strip()]
    _ids = [r[1] for r in _rows]

    check("every scene line is well formed",
          all(len(r) == 4 and r[0] == "pair" for r in _rows),
          str([r for r in _rows if len(r) != 4][:2]))
    check("the spec has the 34 positions the chapter reports",
          len(_rows) == 34, f"{len(_rows)} positions")
    check("17 positions on each bank",
          sum(1 for i in _ids if i[0] == "w") == 17
          and sum(1 for i in _ids if i[0] == "e") == 17,
          "the banks differ in which UR is idle, so an uneven split would "
          "confound bank with idle arm")
    check("no id appears twice", len(set(_ids)) == len(_ids),
          "a duplicate id silently overwrites a capture")

    # The header claims every position was pre-screened against the rasters the
    # validator uses. Check the claim rather than trust it: the same failure
    # went unnoticed in the mustard spec for the life of the file.
    sys.path.insert(0, os.path.join(_FA, "ycb"))
    import screen_ex2_block as _screen                          # REAL screen

    _failed = []
    for _r in _rows:
        _ox, _oy = (float(v) for v in _r[2].split(","))
        _cx, _cy = (float(v) for v in _r[3].split(","))
        _good, _why = _screen.screen(_r[1][0], _ox, _oy, _cx, _cy)
        if not _good:
            _failed.append((_r[1], _why))

    # e10 is expected to fail rule 5: it sits in the band the oblique camera
    # occludes. That is not a defect in the spec -- it is the position section
    # 5.3.1.4 excludes as "the block is hidden behind an arm", and the screen
    # derives it from the rasters alone, without a model. Any OTHER failure is
    # a position that was captured but should not have been.
    check("only the known-occluded position fails the screen",
          [f[0] for f in _failed] == ["e10"],
          "; ".join("%s: %s" % (i, ", ".join(w)) for i, w in _failed)
          or "nothing failed, so the expected e10 failure has gone")

    # The two exclusions the chapter names, tied to the data that records them.
    _inv = os.path.join(_FA, "tables", "ex2_q1", "tab_ex2_q1_inventory.csv")
    if os.path.exists(_inv):
        import csv as _csv
        _rowsi = list(_csv.DictReader(open(_inv)))
        _unusable = {r["position"]: r for r in _rowsi if r["usable"] != "True"}
        check("the inventory holds all 34 positions", len(_rowsi) == 34,
              f"{len(_rowsi)} rows")
        check("exactly the two documented positions are excluded",
              set(_unusable) == {"e02", "e10"},
              f"excluded {sorted(_unusable)}, chapter names two")
        check("each exclusion is excluded for the reason the chapter gives",
              _unusable.get("e10", {}).get("occluded") == "True"
              and "franka_n" not in _unusable.get("e02", {}).get(
                  "legal_small_face", "franka_n"),
              "e10 is the occluded one; e02 is the one where the Franka is "
              "never legal, so no arm choice arises")

# ex2_scenes.txt is the retired mustard pilot and is deliberately not asserted
# on. ycb/README.md records what it is and why it stays.

print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)