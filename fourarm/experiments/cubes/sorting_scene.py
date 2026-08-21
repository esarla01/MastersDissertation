"""Sorting scene: four coloured corner baskets and the category mapping.

Stage 1 of the sorting demo. Baskets are VISUAL pads only (no collision), so
a block set down on one rests on the table surface exactly as before and the
kinematic set-down needs no changes. Each basket sits in its own lock zone
and is reachable by one UR and one Franka (verified offline), so all four
arms can participate and the four sorting streams never contend for a zone.

CATEGORY_BASKET is the ground truth: which colour belongs in which basket.
Stage 1 uses it directly (the oracle). Stage 2 gives the VLM only the basket
descriptions and lets it choose; the oracle then serves as scoring truth and
as the rule-fallback's knowledge.
"""

import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg

from core.cell import cell_config as C

# One basket per corner zone. Positions verified: each in its own quadrant
# zone, each reachable by the nearby UR and the nearby Franka.
BASKETS = {
    "basket_red":    {"pos": (-0.55,  0.50), "zone": "nw", "rgb": (0.80, 0.12, 0.12)},
    "basket_green":  {"pos": ( 0.55,  0.50), "zone": "ne", "rgb": (0.15, 0.65, 0.20)},
    "basket_blue":   {"pos": (-0.55, -0.50), "zone": "sw", "rgb": (0.15, 0.30, 0.80)},
    "basket_yellow": {"pos": ( 0.55, -0.50), "zone": "se", "rgb": (0.85, 0.75, 0.10)},
}

# ground truth: which block colour belongs in which basket
CATEGORY_BASKET = {
    "red": "basket_red",
    "green": "basket_green",
    "blue": "basket_blue",
    "yellow": "basket_yellow",
}

BASKET_SIZE = (0.26, 0.26, 0.008)      # a thin square pad


def oracle_dest(color):
    """The ground-truth destination for a block colour (stage-1 allocator
    knowledge, stage-2 scoring truth)."""
    return BASKETS[CATEGORY_BASKET[color]]["pos"]


def add_baskets(scene_cfg):
    """Attach the four basket pads to the scene config. Visual only: no
    collision, so set-down physics is unchanged."""
    from core.cell.scene_cfg import add_basket_walls
    for name, spec in BASKETS.items():
        x, y = spec["pos"]
        add_basket_walls(scene_cfg, name, x, y)   # shared wall size
        setattr(scene_cfg, name, AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/" + name,
            init_state=AssetBaseCfg.InitialStateCfg(
                pos=(x, y, C.TABLE_H + BASKET_SIZE[2] / 2)),
            spawn=sim_utils.CuboidCfg(
                size=BASKET_SIZE,
                visual_material=sim_utils.PreviewSurfaceCfg(
                    diffuse_color=spec["rgb"]),
            ),
        ))
    return list(BASKETS)