# figures/ — two published, several cut

The thesis prints **two** figures, both simulator captures rather than plots.
Chapter 4 has none.

| | Source | Reproducible |
|---|---|---|
| Figure 3.1, the cell | `thesis/workspace.png` | No generator; captured by hand. See `thesis/README.md` |
| Figure 5.1, the resting faces | `out/ex2_capture_block/e00_{U,L,S}.png` | `ycb/capture_ex2_scene.py --spec ycb/ex2_block.txt`. Byte-identical to the thesis copies |

Everything else here — `ex1_*.csv`, `ex2_q1/`, `ex2_q2/` — is data for figures
that were **generated and then cut before submission**. They plot verified
numbers but appear nowhere in the thesis. They are kept so the numbers are not
lost, and listed here so the files are not mistaken for the source of a
published figure.

`_archive/20260827_threeface/` is the withdrawn three-face design, which
Chapter 5 argues from in §5.5 and §5.8.
