"""Scene configuration: table, four arms, object pool, top-down camera.

Arm assets are the STOCK configs used by the official diff-IK tutorial:
FRANKA_PANDA_HIGH_PD_CFG and UR10_CFG from isaaclab_assets, unmodified apart
from base pose and the UR default joint state (its compact ready stance).
No grippers: grasping is kinematic (see arms.py).
"""

import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sensors import TiledCameraCfg
from isaaclab.utils import configclass

from isaaclab_assets import UR10_CFG
from isaaclab_assets.robots.franka import FRANKA_PANDA_HIGH_PD_CFG

from core.cell import cell_config as C


def _arm_cfg(name):
    spec = C.ARMS[name]
    if spec["type"] == "ur10":
        base = UR10_CFG
        init = base.init_state.replace(pos=spec["pos"], rot=spec["rot"],
                                       joint_pos=dict(C.UR_READY_JOINT_POS))
    else:
        base = FRANKA_PANDA_HIGH_PD_CFG
        init = base.init_state.replace(pos=spec["pos"], rot=spec["rot"])
    return base.replace(prim_path="{ENV_REGEX_NS}/" + name, init_state=init)


def _pool_object_cfg(i):
    category = C.OBJECT_CATEGORIES[i % len(C.OBJECT_CATEGORIES)]
    park = (C.PARK_POS[0] + 0.2 * i, C.PARK_POS[1], C.PARK_POS[2])
    return RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/obj_" + f"{i:02d}",
        spawn=sim_utils.CuboidCfg(
            size=(C.OBJECT_SIZE,) * 3,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.05),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            physics_material=sim_utils.RigidBodyMaterialCfg(
                static_friction=1.0, dynamic_friction=0.9),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=C.CATEGORY_RGB[category]),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=park),
    )


@configclass
class FourArmSceneCfg(InteractiveSceneCfg):
    ground = AssetBaseCfg(prim_path="/World/ground", spawn=sim_utils.GroundPlaneCfg())
    light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(intensity=3000.0, color=(0.9, 0.9, 0.9)),
    )
    table_top = AssetBaseCfg(
        prim_path="/World/Table/Top",
        spawn=sim_utils.CuboidCfg(
            size=C.TABLE_TOP,
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.62, 0.46, 0.30)),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            physics_material=sim_utils.RigidBodyMaterialCfg(
                static_friction=1.0, dynamic_friction=0.9),
        ),
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=(0.0, 0.0, C.TABLE_H - C.TABLE_TOP[2] / 2)),
    )

    ur_w = _arm_cfg("ur_w")
    ur_e = _arm_cfg("ur_e")
    franka_s = _arm_cfg("franka_s")
    franka_n = _arm_cfg("franka_n")

    # Top-down camera, RGB only; consumed by VLM condition V. The RAW
    # frame renders east-up (the rot below is 90 deg about world Y);
    # grab_frame_b64 rotates it 90 deg clockwise so the MODEL always
    # receives a north-up, east-right image matching the map convention.
    # Recorded MP4s keep the raw orientation (rotate in post if needed).
    table_cam = TiledCameraCfg(
        prim_path="{ENV_REGEX_NS}/table_cam",
        offset=TiledCameraCfg.OffsetCfg(
            pos=(0.0, 0.0, 5.0),
            rot=(0.7071, 0.0, 0.7071, 0.0),
            convention="world",
        ),
        data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=32.0, focus_distance=400.0,
            horizontal_aperture=20.955, clipping_range=(0.1, 20.0),
        ),
        width=1024, height=1024,
    )

    # EX2 only. The overhead camera reduces "standing" versus "lying" to a
    # difference in blob size: from directly above, an upright mustard
    # bottle is a ~35 px ellipse and a lying one a ~70 x 35 patch. A flip
    # test run on that image would be asking whether the model can infer
    # pose from a silhouette, which is a much weaker question than whether
    # it can ground capability in visual evidence, and a null result would
    # be unattributable.
    #
    # This camera sits south of the table and above it, looking back at the
    # centre, so an upright bottle reads as upright. It is used ONLY by
    # ycb/capture_ex2_scene.py. table_cam is untouched, so every episode,
    # every harvested probe and conditions V in EX1 and EX3 are unaffected.
    #
    # Geometry: from (0, -2.60, 2.40) toward (0, 0, 0.75) is a look
    # direction of (0, 0.844, -0.536), 32.4 degrees below horizontal. In
    # the world convention the camera looks along +X, so the rotation is
    # Rz(90) then Ry(32.4), giving the quaternion below. Verified by
    # applying it to +X and recovering the look direction exactly.
    ex2_cam = TiledCameraCfg(
        prim_path="{ENV_REGEX_NS}/ex2_cam",
        offset=TiledCameraCfg.OffsetCfg(
            pos=(0.0, -2.60, 2.40),
            rot=(0.6790, -0.1973, 0.1973, 0.6790),
            convention="world",
        ),
        data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=24.0, focus_distance=400.0,
            horizontal_aperture=20.955, clipping_range=(0.1, 20.0),
        ),
        width=1024, height=1024,
    )


def add_object_pool(scene_cfg):
    """Attach the parked object pool. Returns the object attribute names."""
    names = []
    for i in range(C.NUM_POOL_OBJECTS):
        name = f"obj_{i:02d}"
        setattr(scene_cfg, name, _pool_object_cfg(i))
        names.append(name)
    return names


def add_basket_walls(scene_cfg, name, x, y, half=None, height=0.06,
                     thick=0.012, rgb=(0.45, 0.45, 0.48)):
    """Four thin static walls around a basket pad: real collision geometry.

    Why this exists: baskets were flat visual pads with NO collision, so
    nothing retained a delivered object. Objects landed correctly and were
    then knocked out by the next arm reaching in, or tipped and rolled away
    (the tall pitcher ended 24 cm out; the wood block 23 cm). A scoring
    circle cannot do a container's job. With walls, an object that tips or
    is nudged stays inside, and 'in the basket' becomes a physical fact.

    Sizing from measured constraints, not taste:
      half   0.19 m : > CATCH_RADIUS (0.16), so a correctly scored object
                      never rests against a wall; and > ring offset (0.075)
                      + the widest object's half-width, so a placement never
                      collides with a wall.
      height 0.06 m : stops a rolling or sliding object, but far below the
                      height an arm descends from, so reaching in is
                      unaffected.
      restitution 0 : walls absorb, never bounce an object back out.
    """
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    if half is None:
        half = C.BASKET_WALL_HALF
    z = C.TABLE_H + height / 2
    walls = [                                   # east, west, north, south
        (half, 0.0, (thick, 2 * half + thick, height)),
        (-half, 0.0, (thick, 2 * half + thick, height)),
        (0.0, half, (2 * half + thick, thick, height)),
        (0.0, -half, (2 * half + thick, thick, height)),
    ]
    for i, (dx, dy, size) in enumerate(walls):
        wname = f"{name}_wall_{i}"
        setattr(scene_cfg, wname, AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/" + wname,
            init_state=AssetBaseCfg.InitialStateCfg(pos=(x + dx, y + dy, z)),
            spawn=sim_utils.CuboidCfg(
                size=size,
                visual_material=sim_utils.PreviewSurfaceCfg(
                    diffuse_color=rgb, roughness=0.8),
                collision_props=sim_utils.CollisionPropertiesCfg(),
                physics_material=sim_utils.RigidBodyMaterialCfg(
                    static_friction=0.8, dynamic_friction=0.7,
                    restitution=0.0),
            ),
        ))
    return [f"{name}_wall_{i}" for i in range(4)]


def add_pad_markers(scene_cfg, length=0.12, width=0.025, thick=0.006,
                    rgb=(0.95, 0.95, 0.95)):
    """White X marker at every exchange pad (2026-07-25, Erin's design).

    Two crossed bars at +-45 degrees, purely visual, NO collision:
    set-down physics and pad semantics are unchanged. An X reads as "a
    marked spot" even where a basket wall sits nearby, unlike a solid
    tile that reads as floor. Purpose: make the pads visible landmarks
    in the overhead frame (condition V and the E6 anomaly scenario put
    events ON pads; the perception floor test asks about them by name).
    White is absent from every basket colour and object tint.

    Footprint: bar length 0.12 m at 45 degrees spans about 0.10 m, so
    corner-pad markers stay clear of the enlarged basket walls (nearest
    wall inner face is ~0.054 m from the marker tip; positions of pads
    and baskets are FROZEN, only the marker shrank)."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    # z-rotation quaternions (w, x, y, z) for +45 and -45 degrees
    rots = ((0.9238795, 0.0, 0.0, 0.3826834),
            (0.9238795, 0.0, 0.0, -0.3826834))
    names = []
    for pad, spec in C.EXCHANGE_PADS.items():
        x, y = spec["pos"]
        for i, rot in enumerate(rots):
            mname = f"padmark_{pad}_{'ab'[i]}"
            setattr(scene_cfg, mname, AssetBaseCfg(
                prim_path="{ENV_REGEX_NS}/" + mname,
                init_state=AssetBaseCfg.InitialStateCfg(
                    pos=(x, y, C.TABLE_H + thick / 2), rot=rot),
                spawn=sim_utils.CuboidCfg(
                    size=(length, width, thick),
                    visual_material=sim_utils.PreviewSurfaceCfg(
                        diffuse_color=rgb, roughness=0.9),
                ),
            ))
            names.append(mname)
    return names