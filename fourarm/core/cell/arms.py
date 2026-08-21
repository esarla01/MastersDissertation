"""Arm control for the four-arm cell, in one file, kept as close as possible
to Isaac Lab's official differential-IK tutorial:

  tutorial:  https://isaac-sim.github.io/IsaacLab/main/source/tutorials/05_controllers/run_diff_ik.html
  script:    IsaacLab/scripts/tutorials/05_controllers/run_diff_ik.py
  API:       https://isaac-sim.github.io/IsaacLab/main/source/api/lab/isaaclab.controllers.html

Everything follows the tutorial line by line (SceneEntityCfg resolution,
fixed-base Jacobian index = body index minus 1, base-frame commands via
subtract_frame_transforms, DifferentialIKController with the dls method)
with ONE documented addition: the PhysX Jacobian is expressed in the world
frame, and the tutorial's robot stands at the origin so it can use it
directly. Our bases are yawed, so the Jacobian is rotated into the base
frame first. The API docs state the controller assumes nothing about frames
and that consistency is the user's responsibility; this rotation is that
responsibility discharged.

Grasping is kinematic (no grippers, no contact physics): an attached object
is rewritten each tick to hang HANG metres below the end effector. This is a
stated scoping decision; the thesis studies allocation, not grasping.

Two classes only:
  Arm   one robot: set_goal / step (one IK step, does NOT step the sim),
        attach / detach, disable / enable
  Cell  the single shared loop: every arm steps, then the sim steps ONCE,
        which is what makes all four arms move concurrently

Import after the Omniverse app launches.
"""

import torch

from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import matrix_from_quat, quat_inv, subtract_frame_transforms

from core.cell import cell_config as C

class Arm:
    def __init__(self, name, scene, device):
        self.name = name
        self.scene = scene
        self.device = device
        self.robot = scene[name]

        # Joint / end-effector resolution, exactly as in the tutorial.
        info = C.ARM_TYPES[C.ARMS[name]["type"]]
        entity = SceneEntityCfg(name, joint_names=info["joint_names"],
                                body_names=[info["ee_body"]])
        entity.resolve(scene)
        self.joint_ids = entity.joint_ids
        self.ee_body = entity.body_ids[0]
        self.ee_jacobi = self.ee_body - 1          # fixed base, per the tutorial

        # Position-only command (documented option of the controller cfg).
        # Orientation is irrelevant here: grasping is kinematic and carried
        # objects hang in world coordinates, so commanding a strict tool
        # orientation only forces the dls solver into position/orientation
        # compromises (seen as a persistent ~6 cm residual near the bases).
        self.ik = DifferentialIKController(
            DifferentialIKControllerCfg(command_type="position",
                                        use_relative_mode=False,
                                        ik_method="dls"),
            num_envs=1, device=device,
        )
        self.disabled = False
        self._goal = None                           # (pos tuple, quat tuple)
        self._carried = None                        # (name, asset) or None
        self._carry_off = (0.0, 0.0)                # grasp-time XY offset, EE to object

        # D1 travel distance: cumulative EE path length in metres, summed
        # every Cell.tick with no state gating (idle servo jitter is
        # negligible; per-task splits derivable offline from the events).
        self.travel_m = 0.0
        self._last_ee_w = None                      # previous tick EE position

    # -------------------------------------------------------------- state --
    def ee_pos_w(self):
        return self.robot.data.body_state_w[:, self.ee_body, 0:3]

    def error(self):
        """Distance from the end effector to the current goal, or None."""
        if self._goal is None:
            return None
        gp = torch.tensor([self._goal], device=self.device, dtype=torch.float32)
        return float(torch.norm(self.ee_pos_w() - gp))

    # -------------------------------------------------------------- goals --
    def set_goal(self, x, y, z):
        if not self.disabled:
            self._goal = (float(x), float(y), float(z))

    def clear_goal(self):
        self._goal = None

    # --------------------------------------------------------------- step --
    def step(self):
        """One differential-IK step toward the goal. Sets joint targets only;
        the Cell steps the sim. Returns the current error, or None if idle."""
        if self.disabled or self._goal is None:
            return None

        root = self.robot.data.root_state_w[:, 0:7]
        gp = torch.tensor([self._goal], device=self.device, dtype=torch.float32)
        identity = torch.tensor([[1.0, 0.0, 0.0, 0.0]], device=self.device)

        # Current EE pose in the BASE frame (tutorial pattern), needed both
        # for the IK compute and for set_command: the controller requires the
        # current EE orientation with position commands (it holds it as the
        # nominal orientation while only position is tracked).
        ee_w = self.robot.data.body_state_w[:, self.ee_body, 0:7]
        ee_pos_b, ee_quat_b = subtract_frame_transforms(
            root[:, 0:3], root[:, 3:7], ee_w[:, 0:3], ee_w[:, 3:7])

        # Goal position in the BASE frame (goal quat is a dummy identity).
        cmd_pos_b, _ = subtract_frame_transforms(
            root[:, 0:3], root[:, 3:7], gp, identity)
        self.ik.set_command(cmd_pos_b, ee_quat=ee_quat_b)

        # PhysX Jacobian (world frame), rotated into the base frame. This is
        # the one addition over the tutorial, required for yawed bases.
        jac = self.robot.root_physx_view.get_jacobians()[
            :, self.ee_jacobi, :, self.joint_ids].clone()
        rot = matrix_from_quat(quat_inv(root[:, 3:7]))
        jac[:, 0:3, :] = torch.bmm(rot, jac[:, 0:3, :])
        jac[:, 3:6, :] = torch.bmm(rot, jac[:, 3:6, :])

        q = self.robot.data.joint_pos[:, self.joint_ids]
        q_des = self.ik.compute(ee_pos_b, ee_quat_b, jac, q)
        self.robot.set_joint_position_target(q_des, joint_ids=self.joint_ids)
        return float(torch.norm(self.ee_pos_w() - gp))

    # ---------------------------------------------------- kinematic grasp --
    def attach(self, obj_name):
        """Attach the object if the EE hovers within tolerance above it AND
        the object is within this arm's grasp-size and payload limits. The
        capability check is what a physical gripper would enforce; with
        kinematic grasping it must be explicit or every arm could lift
        anything."""
        if not C.can_grasp(self.name, obj_name):
            return False
        obj = self.scene[obj_name]
        gap = float(torch.norm(self.ee_pos_w() - obj.data.root_pos_w[:, 0:3]))
        if gap > C.HANG + C.ATTACH_TOL:
            return False
        # Preserve the grasp-time lateral offset. Pinning the object directly
        # under the EE instead would teleport it sideways by up to the stall
        # tolerance in one tick, at table height, and a kinematically driven
        # block slams any neighbour in that jump (the observed slides when a
        # nearby block is picked). With the offset preserved, the block lifts
        # straight up from where it stands. The set-down at placement still
        # puts it exactly on target.
        ee = self.ee_pos_w()[0]
        op = obj.data.root_pos_w[0]
        self._carry_off = (float(op[0] - ee[0]), float(op[1] - ee[1]))
        self._carried = (obj_name, obj)
        return True

    def detach(self, place_xy=None, place_z=None):
        """Release the carried object. With place_xy given (a deliberate
        placement), the object is first SET DOWN kinematically: written to
        rest on the table at that point with zero velocity, then unpinned.
        This mirrors the kinematic grasp and prevents the ejection artifact
        where stall-accepted vertical error left the pinned object
        interpenetrating the table, so PhysX fired it sideways on release.
        place_z is the object's true resting ROOT height (YCB objects rest
        at per-object heights, measured by the probe); omitted, it falls
        back to the cube's resting height, so all existing callers are
        unchanged. A wrong height re-creates the ejection artifact: a soup
        can set down at cube height starts 4 mm inside the table.
        Without place_xy (aborts, D3 drops) the object is released wherever
        it hangs and falls naturally, which is the intended drop behaviour."""
        name = self._carried[0] if self._carried else None
        if self._carried is not None and place_xy is not None:
            _, obj = self._carried
            pose = torch.zeros((1, 7), device=self.device)
            pose[:, 0] = float(place_xy[0])
            pose[:, 1] = float(place_xy[1])
            pose[:, 2] = (float(place_z) if place_z is not None
                          else C.OBJECT_SPAWN_Z + 0.003)
            pose[:, 3] = 1.0
            obj.write_root_pose_to_sim(pose)
            obj.write_root_velocity_to_sim(torch.zeros((1, 6), device=self.device))
        self._carried = None
        self._carry_off = (0.0, 0.0)
        return name

    def update_carried(self):
        """Pin the carried object HANG metres below the EE (identity rotation,
        fine for cubes). Called by the Cell after every physics step."""
        if self._carried is None:
            return
        _, obj = self._carried
        pose = torch.zeros((1, 7), device=self.device)
        pose[:, 0:3] = self.ee_pos_w()
        pose[:, 0] += self._carry_off[0]
        pose[:, 1] += self._carry_off[1]
        pose[:, 2] -= C.HANG
        pose[:, 3] = 1.0
        obj.write_root_pose_to_sim(pose)
        obj.write_root_velocity_to_sim(torch.zeros((1, 6), device=self.device))

    def tuck(self):
        """Fold into the compact idle stance (joint space). Used when parked;
        any subsequent set_goal simply overrides it with IK targets again."""
        stance = C.TUCK_JOINT_POS.get(C.ARMS[self.name]["type"])
        if not stance or self.disabled:
            return
        q = self.robot.data.default_joint_pos.clone()
        for jname, val in stance.items():
            ids, _ = self.robot.find_joints(jname)
            q[:, ids[0]] = val
        self.clear_goal()
        self.robot.set_joint_position_target(q)
        self._tuck_q = q                     # remembered so tuck_settled()
                                             # can VERIFY arrival (rule 18:
                                             # fixed-duration resets lie)

    def tuck_settled(self, tol=0.05):
        """True once every joint is within tol of the last tuck target
        (or no tuck was ever commanded)."""
        if getattr(self, "_tuck_q", None) is None:
            return True
        import torch
        q = self.robot.data.joint_pos[0, self.joint_ids]
        target = self._tuck_q[0, self.joint_ids]
        return bool(torch.max(torch.abs(q - target)) < tol)

    # ----------------------------------------------------------- disruption --
    def disable(self, drop=True):
        """D3: freeze at the current configuration; optionally drop cargo."""
        self.disabled = True
        self._goal = None
        if drop:
            self.detach()
        hold = self.robot.data.joint_pos[:, self.joint_ids].clone()
        self.robot.set_joint_position_target(hold, joint_ids=self.joint_ids)

    def enable(self):
        self.disabled = False


class Cell:
    """The single shared loop: every arm steps, then the sim steps once."""

    def __init__(self, sim, scene, arms: dict):
        self.sim = sim
        self.scene = scene
        self.arms = arms
        self.dt = sim.get_physics_dt()
        self.recorder = None                 # optional recorder.Recorder

    def tick(self, render=True):
        errors = {name: arm.step() for name, arm in self.arms.items()}
        self.scene.write_data_to_sim()
        self.sim.step(render=render)
        self.scene.update(self.dt)
        for arm in self.arms.values():
            arm.update_carried()
        for arm in self.arms.values():              # D1 travel accumulator
            p = arm.ee_pos_w()[0]
            if arm._last_ee_w is not None:
                arm.travel_m += float(torch.norm(p - arm._last_ee_w))
            arm._last_ee_w = p.clone()
        if self.recorder is not None:
            self.recorder.grab(self.scene)
        return errors

    def run_until(self, max_ticks=1200, tol=C.REACH_TOL, probe_every=120):
        """Tick until every goal is reached. An arm that arrives within tol
        has its goal CLEARED (it then holds its last joint targets), so
        finished arms neither fidget nor block the others. Returns
        (all_reached, last_errors)."""
        last = {}
        for t in range(max_ticks):
            last = self.tick(render=(t % 2 == 0))
            for n, e in last.items():
                if e is not None and e < tol:
                    self.arms[n].clear_goal()
            if probe_every and t % probe_every == 0:
                line = "  ".join(f"{n}:{'--' if e is None else f'{e:.3f}'}"
                                 for n, e in last.items())
                print(f"    [tick {t:4d}] {line}", flush=True)
            if not any(a._goal is not None for a in self.arms.values()):
                return True, last
        return False, last

    def hold(self, ticks, render=True):
        for c in range(ticks):
            self.tick(render=render and (c % 2 == 0))

    def settle(self):
        """Hold every arm at its default joint state (the scene config sets
        the UR ready pose as its default) until the cell is at rest."""
        for _ in range(C.SETTLE_STEPS):
            for arm in self.arms.values():
                arm.robot.set_joint_position_target(
                    arm.robot.data.default_joint_pos)
            self.scene.write_data_to_sim()
            self.sim.step(render=False)
            self.scene.update(self.dt)