import test from 'node:test';
import assert from 'node:assert/strict';
import { EMPTY_GRACE_MS, isExpired } from './lifecycle.mjs';
import {
  MAX_CODE_ATTEMPTS, RoomCodeError, claimRoomCode, createRoomWithUniqueCode, generateRoomCode,
} from './room-code.mjs';

const NOW = 2_000_000_000;
const candidateWith = code => ({ code, hostToken: `host-${code}`, createdAt: NOW, touchedAt: NOW });

// Stand-in for "one Durable Object per room code".
function registryFixture(initial = {}) {
  const rooms = new Map(Object.entries(initial));
  const claim = candidate => {
    const result = claimRoomCode(rooms.get(candidate.code), candidate, NOW);
    if (result.claimed) rooms.set(candidate.code, result.room);
    return Promise.resolve(result.claimed);
  };
  return { rooms, claim };
}

const sequence = codes => {
  const attempts = [];
  const makeCandidate = () => {
    const code = codes[attempts.length] ?? `9${attempts.length}0000`;
    attempts.push(code);
    return candidateWith(code);
  };
  return { attempts, makeCandidate };
};

test('room codes are six digits drawn from 100000 up to 999999', () => {
  const calls = [];

  const code = generateRoomCode((min, max) => { calls.push([min, max]); return 424242; });

  assert.equal(code, '424242');
  assert.deepEqual(calls, [[100000, 1000000]]);
  assert.match(generateRoomCode(), /^[1-9]\d{5}$/);
});

test('a free code is claimed and the new room starts counting as empty', () => {
  const { claimed, room } = claimRoomCode(undefined, candidateWith('111111'), NOW);

  assert.equal(claimed, true);
  assert.equal(room.emptySince, NOW);
  assert.equal(isExpired(room, NOW + EMPTY_GRACE_MS), true, 'a room nobody joins goes away');
});

test('a live room keeps its code', () => {
  const live = { ...candidateWith('111111'), emptySince: null };

  const result = claimRoomCode(live, candidateWith('111111'), NOW + 1000);

  assert.equal(result.claimed, false);
  assert.equal(result.room, live);
});

test('an expired room gives its code up', () => {
  const stale = { ...candidateWith('111111'), emptySince: NOW - EMPTY_GRACE_MS - 1 };

  const result = claimRoomCode(stale, candidateWith('111111'), NOW);

  assert.equal(result.claimed, true);
  assert.equal(result.room.hostToken, 'host-111111');
});

test('the first free code is used on the first attempt', async () => {
  const { attempts, makeCandidate } = sequence(['111111']);
  const { claim } = registryFixture();

  const room = await createRoomWithUniqueCode({ makeCandidate, claim });

  assert.equal(room.code, '111111');
  assert.equal(attempts.length, 1);
});

test('collisions are retried with a fresh candidate until a free code turns up', async () => {
  const live = { ...candidateWith('111111'), emptySince: null };
  const { attempts, makeCandidate } = sequence(['111111', '111111', '222222']);
  const { claim, rooms } = registryFixture({ 111111: live });

  const room = await createRoomWithUniqueCode({ makeCandidate, claim });

  assert.equal(room.code, '222222');
  assert.equal(attempts.length, 3);
  assert.equal(rooms.get('111111'), live, 'the existing room is untouched');
});

test('it gives up after the attempt limit with a 503', async () => {
  const live = { ...candidateWith('111111'), emptySince: null };
  const { attempts, makeCandidate } = sequence(Array(10).fill('111111'));
  const { claim } = registryFixture({ 111111: live });

  await assert.rejects(
    createRoomWithUniqueCode({ makeCandidate, claim }),
    error => error instanceof RoomCodeError && error.status === 503,
  );
  assert.equal(attempts.length, MAX_CODE_ATTEMPTS);
});

test('the attempt limit can be overridden', async () => {
  const live = { ...candidateWith('111111'), emptySince: null };
  const { attempts, makeCandidate } = sequence(Array(10).fill('111111'));
  const { claim } = registryFixture({ 111111: live });

  await assert.rejects(createRoomWithUniqueCode({ makeCandidate, claim, maxAttempts: 2 }), RoomCodeError);
  assert.equal(attempts.length, 2);
});
