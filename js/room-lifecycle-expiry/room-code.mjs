// Giving a new room a code that no live room is using.
// Rooms are addressed by a short numeric code, so collisions are expected and retried.

import { randomInt } from 'node:crypto';
import { isExpired } from './lifecycle.mjs';

export const MAX_CODE_ATTEMPTS = 5;
const CODE_MIN = 100000;
const CODE_MAX_EXCLUSIVE = 1000000;

export class RoomCodeError extends Error {
  constructor(message, status = 503) {
    super(message);
    this.status = status;
  }
}

export const generateRoomCode = (randomIntImpl = randomInt) =>
  String(randomIntImpl(CODE_MIN, CODE_MAX_EXCLUSIVE));

/**
 * Whether `candidate` may take its code. A live room keeps the code; an expired one
 * gives it up. A new room starts as "empty", so one that nobody joins expires on its own.
 */
export function claimRoomCode(existing, candidate, now) {
  if (existing && !isExpired(existing, now)) return { claimed: false, room: existing };
  return { claimed: true, room: { ...candidate, emptySince: now } };
}

/**
 * Try up to `maxAttempts` fresh candidates. `claim(candidate)` resolves true when the
 * code was free (in production: ask the object that owns that code).
 */
export async function createRoomWithUniqueCode({ makeCandidate, claim, maxAttempts = MAX_CODE_ATTEMPTS }) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const candidate = makeCandidate();
    if (await claim(candidate)) return candidate;
  }
  throw new RoomCodeError('could not allocate a room code, try again');
}
