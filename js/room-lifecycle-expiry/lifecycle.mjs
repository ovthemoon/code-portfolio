// When a room stops existing. A room nobody uses must not keep costing anything.

export const MAX_ROOM_AGE_MS = 24 * 60 * 60 * 1000;
export const MAX_IDLE_MS = 6 * 60 * 60 * 1000;
export const EMPTY_GRACE_MS = 10 * 60 * 1000;

/**
 * Earliest of: maximum age, idle time since the last activity, and the grace period
 * after the room became empty. `emptySince` null or missing means "not empty".
 */
export function roomExpiry(room) {
  return Math.min(
    room.createdAt + MAX_ROOM_AGE_MS,
    room.touchedAt + MAX_IDLE_MS,
    room.emptySince == null ? Infinity : room.emptySince + EMPTY_GRACE_MS,
  );
}

export const isExpired = (room, now) => roomExpiry(room) <= now;

/**
 * Update the empty clock from whether any authenticated connection is present.
 * Only authenticated connections count: plain requests and failed handshakes cannot
 * extend the grace. Returns the same object when nothing changed, so the caller
 * can tell with `next !== room` whether to save.
 */
export function trackOccupancy(room, occupied, now) {
  if (occupied) return room.emptySince === null ? room : { ...room, emptySince: null };
  return room.emptySince != null ? room : { ...room, emptySince: now };
}
