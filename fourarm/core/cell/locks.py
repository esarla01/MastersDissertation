"""Zone locks for workspace deconfliction (Layer 2).

The table is partitioned into five geometric lock zones: a disc at the
centre and the four quadrants around it. Every (x, y) maps to exactly one
zone. An arm must hold the lock of the zone containing its current motion
target; if the lock is taken it waits (BLOCKED) and the wait is metered,
because blocking time is a core thesis metric.

Zones are deliberately geometric rather than raster-derived: five names are
enough for mutual exclusion, and the rasters stay in charge of feasibility
(who CAN reach a point) via zones.ZoneMap.
"""

import math

from core.cell import cell_config as C


def zone_of(x, y):
    """Name of the lock zone containing (x, y)."""
    if math.hypot(x, y) <= C.CENTER_RADIUS:
        return "center"
    if x >= 0:
        return "ne" if y >= 0 else "se"
    return "nw" if y >= 0 else "sw"


class ZoneLocks:
    def __init__(self):
        self.holder = {}                      # zone -> arm name
        # Advisory reservations: zone -> ordered arm names with ASSIGNED
        # work whose path will need the zone but who have not physically
        # acquired it yet. Reservations never gate acquire (the safety
        # layer is unchanged); they make inbound intent visible to
        # contention-aware allocators (B2), the VLM state, and the ledger.
        self.reservations = {}
        self.acquires = 0
        self.denials = 0
        # Time-stamped ledger of every ownership change, for cross-reading
        # against proximity events when diagnosing arm-arm near misses.
        # `tick` is set by the Coordinator each cycle.
        self.tick = 0
        self.ledger = []

    def acquire(self, zone, arm):
        """True if the arm now holds (or already held) the zone."""
        owner = self.holder.get(zone)
        if owner is None:
            self.holder[zone] = arm
            self.acquires += 1
            self.ledger.append({"tick": self.tick, "action": "acquire",
                                "zone": zone, "arm": arm})
            # intent became possession: the reservation is consumed
            q = self.reservations.get(zone, [])
            if arm in q:
                q.remove(arm)
                if not q:
                    del self.reservations[zone]
            return True
        if owner == arm:
            return True
        self.denials += 1
        return False

    def reserve(self, zone, arm):
        """Declare inbound intent (idempotent). Advisory only."""
        q = self.reservations.setdefault(zone, [])
        if arm not in q:
            q.append(arm)
            self.ledger.append({"tick": self.tick, "action": "reserve",
                                "zone": zone, "arm": arm})

    def unreserve(self, zone, arm):
        q = self.reservations.get(zone, [])
        if arm in q:
            q.remove(arm)
            self.ledger.append({"tick": self.tick, "action": "unreserve",
                                "zone": zone, "arm": arm})
            if not q:
                del self.reservations[zone]

    def inbound_for(self, zone):
        """Arms with declared inbound intent on the zone (excludes holder)."""
        return list(self.reservations.get(zone, []))

    def is_contended(self, zone, arm):
        """True if the zone is held or reserved by anyone OTHER than arm."""
        owner = self.holder.get(zone)
        if owner is not None and owner != arm:
            return True
        return any(a != arm for a in self.reservations.get(zone, []))

    def release(self, zone, arm):
        if self.holder.get(zone) == arm:
            del self.holder[zone]
            self.ledger.append({"tick": self.tick, "action": "release",
                                "zone": zone, "arm": arm})

    def release_all(self, arm):
        """Free every zone the arm holds AND every reservation it made
        (task end, requeue, give-up, or D3)."""
        for zone in [z for z, a in self.holder.items() if a == arm]:
            del self.holder[zone]
            self.ledger.append({"tick": self.tick, "action": "release",
                                "zone": zone, "arm": arm})
        for zone in [z for z, q in self.reservations.items() if arm in q]:
            self.unreserve(zone, arm)

    def held_by(self, arm):
        return [z for z, a in self.holder.items() if a == arm]