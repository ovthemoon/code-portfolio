import test from 'node:test';
import assert from 'node:assert/strict';
import {
  EMPTY_GRACE_MS, MAX_IDLE_MS, MAX_ROOM_AGE_MS,
  isExpired, roomExpiry, trackOccupancy,
} from './lifecycle.mjs';

const T0 = 1_000_000_000;
const room = overrides => ({ createdAt: T0, touchedAt: T0, emptySince: null, ...overrides });

test('a room expires at the earliest of age, idle time and empty grace', () => {
  assert.equal(roomExpiry(room()), T0 + MAX_IDLE_MS);
  assert.equal(roomExpiry(room({ touchedAt: T0 + MAX_ROOM_AGE_MS })), T0 + MAX_ROOM_AGE_MS);
  assert.equal(roomExpiry(room({ emptySince: T0 + 1000 })), T0 + 1000 + EMPTY_GRACE_MS);
});

test('activity pushes the idle limit forward, but never past the maximum age', () => {
  const oneHour = 60 * 60 * 1000;

  assert.equal(roomExpiry(room({ touchedAt: T0 + oneHour })), T0 + oneHour + MAX_IDLE_MS);
  assert.equal(roomExpiry(room({ touchedAt: T0 + MAX_ROOM_AGE_MS - 1000 })), T0 + MAX_ROOM_AGE_MS);
});

test('a missing emptySince (older rooms) means the empty grace does not apply', () => {
  const legacy = { createdAt: T0, touchedAt: T0 };

  assert.equal(roomExpiry(legacy), T0 + MAX_IDLE_MS);
});

test('isExpired is true at the expiry time and after', () => {
  const r = room({ emptySince: T0 });

  assert.equal(isExpired(r, T0 + EMPTY_GRACE_MS - 1), false);
  assert.equal(isExpired(r, T0 + EMPTY_GRACE_MS), true);
});

test('the empty clock starts when the last authenticated connection leaves', () => {
  const next = trackOccupancy(room(), false, T0 + 5000);

  assert.equal(next.emptySince, T0 + 5000);
});

test('a connection arriving stops the empty clock', () => {
  const next = trackOccupancy(room({ emptySince: T0 + 5000 }), true, T0 + 9000);

  assert.equal(next.emptySince, null);
});

test('observing an already-empty room again does not extend the grace', () => {
  const empty = room({ emptySince: T0 + 5000 });

  const later = trackOccupancy(empty, false, T0 + 400_000);

  assert.equal(later, empty);
  assert.equal(roomExpiry(later), T0 + 5000 + EMPTY_GRACE_MS);
});

test('an occupied room that is already marked occupied is returned unchanged', () => {
  const occupied = room();

  assert.equal(trackOccupancy(occupied, true, T0 + 1), occupied);
});

test('leaving and rejoining restarts the grace from the new departure', () => {
  let r = trackOccupancy(room(), false, T0 + 1000);
  r = trackOccupancy(r, true, T0 + 2000);
  r = trackOccupancy(r, false, T0 + 50_000);

  assert.equal(roomExpiry(r), T0 + 50_000 + EMPTY_GRACE_MS);
});

test('an older room without emptySince is migrated on the first observation', () => {
  const legacy = { createdAt: T0, touchedAt: T0 };

  assert.equal(trackOccupancy(legacy, true, T0 + 1).emptySince, null);
  assert.equal(trackOccupancy(legacy, false, T0 + 7).emptySince, T0 + 7);
});

test('trackOccupancy does not modify the room it was given', () => {
  const frozen = Object.freeze(room());

  const next = trackOccupancy(frozen, false, T0 + 1);

  assert.notEqual(next, frozen);
  assert.equal(frozen.emptySince, null);
});
