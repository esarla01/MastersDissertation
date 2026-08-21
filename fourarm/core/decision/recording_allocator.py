"""Record decision states from ANY allocator, including the built-in rule.

WHY THIS EXISTS. A probe set stores STATES, not decisions: every rung is
re-rendered from the state at replay time, so which allocator produced a
state has no bearing on what EX1 or EX3 can ask of it. Until now the audit
trail was written inside VLMAllocator, so the only way to harvest was to
run the model. The 2026-08-14 harvest cost 675 model calls and 45 minutes
of latency to yield 27 distinct option sets, and it would have cost that
again for every layout compared. b1 is not an allocator object at all, it
is Coordinator's default rule_based_allocate function, so there was
nothing to hang a trail on.

This wrapper is a callable with rule_based_allocate's exact signature. It
writes the consult record, then delegates and returns the delegate's
result UNCHANGED, so the episode is bit-identical to one run without it.
vlm_allocator.py is untouched, so the byte-identity acceptance test still
holds against the VLM path.

WHAT IT DOES NOT DO. It writes no "messages" field, because no model was
asked. probe_store reads state, positions_exact, frames and provenance, so
a harvested probe is complete; verify_trail's prompt half has nothing to
compare against on these trails and should not be run on them. That is the
honest boundary: these trails are for harvesting states, not for
reproducing a model's inputs.

Usage in a runner:

    from core.decision.recording_allocator import RecordingAllocator
    alloc = RecordingAllocator(lambda: holder["c"], engine,
                               zonemap=zonemap, baskets=BASKETS,
                               audit_dir=f"out/{OUT_STEM}_frames",
                               cameras=("table_cam", "ex2_cam"))
    coord = Coordinator(cell, zonemap, allocate=alloc, engine=engine)
    holder["c"] = coord
"""

import base64
import json
import os

from core.control.tasks import rule_based_allocate
from core.decision.state_builder import build_state, grab_frame_b64


class RecordingAllocator:
    """Delegating allocator that writes one consult record per call."""

    def __init__(self, coord_ref, engine, zonemap=None, baskets=None,
                 audit_dir=None, cameras=("table_cam",), delegate=None,
                 enriched=True, source_note=""):
        self.coord_ref = coord_ref
        self.engine = engine
        self.zonemap = zonemap
        self.baskets = baskets
        self.audit_dir = audit_dir
        self.cameras = tuple(cameras or ())
        # Default delegate is the SAME function Coordinator uses when no
        # allocator is passed, so wrapping b1 changes nothing about b1.
        self.delegate = delegate or rule_based_allocate
        self.enriched = enriched
        self.source_note = source_note
        self._seq = 0
        self._round = 0
        self._last_sig = None
        if self.audit_dir:
            os.makedirs(self.audit_dir, exist_ok=True)

    def __call__(self, task, obj_xy, idle_arms, zonemap, disabled=()):
        self._record_if_new()
        # Signature-tolerant delegation, mirroring Coordinator's own
        # try/except: an allocator predating the disabled argument must
        # still work through the wrapper.
        try:
            return self.delegate(task, obj_xy, idle_arms, zonemap,
                                 disabled=disabled)
        except TypeError:
            return self.delegate(task, obj_xy, idle_arms, zonemap)

    def _signature(self, coord):
        """The decision-relevant state: idle arms and assignable tasks.

        This is VLMAllocator's gate, reused deliberately. Coordinator calls
        allocate once per open task per round, so recording per call writes
        one state and two camera renders for every task considered, and a
        state that lingers is re-recorded every physics step. That is the
        same runaway the VLM allocator's own comment describes as "the
        observed hang", and it is what made a recorded b1 episode slower
        than the model-driven one it was meant to replace.

        Gating on this signature records ONE state per genuinely distinct
        decision situation, which is also the right unit for a probe set:
        the per-task calls within a round all see the same state, so the
        extra copies carried no information and would have skewed every
        rate computed over the set toward whichever situation lingered.
        """
        done_ids = {t.id for t in coord.pool if t.done}
        ready = frozenset(
            t.id for t in coord.pool
            if not t.done and not t.failed and not t.claimed
            and (t.waiting_on is None or t.waiting_on in done_ids))
        idle = frozenset(n for n, ag in coord.agents.items()
                         if ag.state == "IDLE" and not ag.arm.disabled)
        return (idle, ready)

    def _record_if_new(self):
        """Write one consult record per distinct decision situation."""
        if not self.audit_dir:
            return
        try:
            coord = self.coord_ref()
            sig = self._signature(coord)
            if sig == self._last_sig:
                return
            self._last_sig = sig
            self._round += 1
        except Exception as e:
            if not getattr(self, "_warned", False):
                self._warned = True
                print(f"[recording_allocator] gate failed: "
                      f"{type(e).__name__}: {e}")
            return
        self._record(coord)

    def _record(self, coord):
        """Write one consult record. Never raises: a failed audit write
        must not kill an episode that is otherwise progressing."""
        try:
            self._seq += 1
            state = build_state(coord, self.engine, tick=self._round,
                                baskets=self.baskets,
                                zonemap=(self.zonemap if self.enriched
                                         else None))
            stem = f"consult_{self._seq:03d}_round{self._round}"
            frames, frame_errors = {}, {}
            for cam in self.cameras:
                try:
                    b64 = grab_frame_b64(coord.cell.scene, camera=cam,
                                         rot_k=(-1 if cam == "table_cam"
                                                else 0))
                    fn = f"{stem}_{cam}.png"
                    with open(os.path.join(self.audit_dir, fn), "wb") as f:
                        f.write(base64.b64decode(b64))
                    frames[cam] = fn
                except Exception as e:
                    frame_errors[cam] = f"{type(e).__name__}: {e}"
            rec = {
                "seq": self._seq,
                "round": self._round,
                # No model was asked, so condition is neither A nor V. A
                # distinct label keeps these trails from being pooled with
                # model-sourced ones by accident.
                "condition": "REC",
                "image_file": None,
                "frames": frames,
                "frame_errors": frame_errors,
                "prompt_version": None,
                "enriched": self.enriched,
                "eligible": False,
                "state": state,
                "positions_exact": self._positions(coord),
                "position_errors": {},
                "model": {"model": None,
                          # A function delegate has __name__; an allocator
                          # OBJECT (random, opt) does not, so fall back to
                          # its class name rather than raising inside the
                          # audit write.
                          "alias": f"recording:"
                                   f"{getattr(self.delegate, '__name__', None) or type(self.delegate).__name__}"},
                "note": self.source_note,
            }
            with open(os.path.join(self.audit_dir, "consults.jsonl"),
                      "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:
            # Surfaced once so a silently empty trail is impossible.
            if not getattr(self, "_warned", False):
                self._warned = True
                print(f"[recording_allocator] audit write failed: "
                      f"{type(e).__name__}: {e}")

    @staticmethod
    def _positions(coord):
        """Exact object coordinates, beyond the rounded ones in the state.

        probe_store stores these so a probe can be re-validated against
        the true geometry rather than the prompt's rounded numbers.
        """
        out = {}
        for t in coord.pool:
            try:
                p = coord.cell.scene[t.obj].data.root_pos_w[0]
                out[t.obj] = [float(p[0]), float(p[1]), float(p[2])]
            except Exception:
                pass
        return out