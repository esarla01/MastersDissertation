# The two figures the thesis prints

Chapter 4 carries no figures. The thesis prints two, both simulator captures
rather than plots.

| Figure | File in the thesis | Source here | Reproducible |
|---|---|---|---|
| 3.1, the four-arm cell | `figures/workspace.png` | `workspace.png`, beside this README | **No generator.** Captured by hand from Isaac Sim |
| 5.1, the three resting faces | `figures/e00_{U,L,S}.png` | `out/ex2_capture_block/e00_{U,L,S}.png` | `ycb/capture_ex2_scene.py --spec ycb/ex2_block.txt` |

Figure 5.1's three panels are **byte-identical** to the committed captures, so
that figure traces end to end: spec, script, output, thesis.

Figure 3.1 does not. No script in this repository produces it, and until
2026-09-11 the image was not here either — only in the thesis tree. It is
copied in so the repository is self-contained, and recorded as a manual
artefact rather than left looking reproducible.

Re-creating it means loading the cell in Isaac Sim and capturing the viewport
by hand. The thesis applies `trim=0 172 0 150, clip` to it, so the committed
file is the untrimmed original.

| File | sha256 (first 16) |
|---|---|
| `workspace.png` | `7f39ea28453608a1` |
| `out/ex2_capture_block/e00_U.png` | `25b67757ea09f58b` |
| `out/ex2_capture_block/e00_L.png` | `ddf2293a587736cd` |
| `out/ex2_capture_block/e00_S.png` | `901b5f857002c10f` |
