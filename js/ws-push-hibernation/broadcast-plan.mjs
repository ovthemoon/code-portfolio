// Pure decisions behind "push only on change, wake only on alarm".
// The Durable Object (see excerpt/relay-room.js) feeds these functions with the
// per-socket attachments and room timers, then performs the sends and setAlarm.

export const PRESENCE_GRACE_MS = 15_000;
export const CLOSED_LINGER_MS = 30 * 60 * 1000;

/**
 * Decide which sockets need a state message for `revision`.
 * Each session is a socket's saved attachment: { id, authenticated, revision }.
 * Returns the ids to send to and the sessions with the delivered revision recorded.
 * `forcedId` is sent to even when its revision is already current (the socket
 * that just authenticated, or the one whose request failed).
 */
export function planBroadcast(sessions, revision, forcedId = null) {
  const sendTo = [];
  const updated = sessions.map(session => {
    if (!session.authenticated) return session;
    if (session.id !== forcedId && session.revision === revision) return session;
    sendTo.push(session.id);
    return { ...session, revision };
  });
  return { sendTo, sessions: updated };
}

/**
 * The single alarm time: the earliest of every deadline that needs the object awake.
 *  - game timers (only while running): `deadline`, and `nextRoundAt` between rounds
 *  - `unauthDeadlines`: handshake deadlines of sockets that have not authenticated
 *  - `absentSeenAt`: last-seen times of players whose socket dropped (grace expiry)
 *  - room lifetime: `expiresAt`, or touchedAt + linger once the room is closed
 * Never earlier than now + 1. Returns null if nothing is pending.
 */
export function nextAlarmAt({
  now, closed, timersRunning, deadline, nextRoundAt,
  touchedAt, expiresAt, unauthDeadlines, absentSeenAt,
}) {
  const gameAlarm = timersRunning
    ? Math.min(deadline ?? Infinity, nextRoundAt ?? Infinity)
    : Infinity;
  const authAlarm = Math.min(Infinity, ...unauthDeadlines);
  const graceAlarm = Math.min(
    Infinity,
    ...absentSeenAt.map(seenAt => seenAt + PRESENCE_GRACE_MS).filter(at => at > now),
  );
  const lifetimeAlarm = closed
    ? touchedAt + CLOSED_LINGER_MS
    : Math.min(expiresAt, gameAlarm);
  const earliest = Math.min(authAlarm, graceAlarm, lifetimeAlarm);
  return Number.isFinite(earliest) ? Math.max(now + 1, earliest) : null;
}

/** Same as nextAlarmAt, plus whether storage.setAlarm needs to be called. */
export function planAlarm(previousAt, inputs) {
  const at = nextAlarmAt(inputs);
  return { at, shouldSet: at !== null && at !== previousAt };
}
