import test from 'node:test';
import assert from 'node:assert/strict';
import { ActionError, HANDLED_LIMIT, act, createRoom } from './room-actions.mjs';

const NOW = 1_000_000;
const host = { kind: 'host' };
const board = { kind: 'board' };
const player = number => ({ kind: 'player', number });

const request = (room, action, extra = {}) => ({
  action, id: `request_${Math.random().toString(36).slice(2, 12)}`,
  stage: room.stage, roundId: room.roundId, ...extra,
});
const status = code => error => error instanceof ActionError && error.status === code;

test('a repeated request id is applied once and answered as success', () => {
  const room = createRoom(NOW);
  const req = request(room, 'award', { points: 3 });

  const first = act(room, host, req, NOW);
  const second = act(first.room, host, req, NOW + 10);

  assert.equal(first.replayed, false);
  assert.equal(second.replayed, true);
  assert.equal(second.room.score, 3);
  assert.equal(second.room.history.length, 1);
  assert.equal(second.room.revision, first.room.revision);
});

test('a replay is checked before the stage, so it stays success after the stage moved on', () => {
  const room = createRoom(NOW);
  const req = request(room, 'award', { points: 2 });
  const { room: after } = act(room, host, req, NOW);

  assert.notEqual(after.stage, req.stage);
  assert.doesNotThrow(() => act(after, host, req, NOW + 10));
});

test('a new id that carries an old stage is rejected as stale', () => {
  const room = createRoom(NOW);
  const { room: after } = act(room, host, request(room, 'award', { points: 3 }), NOW);

  const stale = { ...request(room, 'award', { points: 3 }), id: 'another_request_1' };

  assert.throws(() => act(after, host, stale, NOW + 10), status(409));
});

test('a new id that carries an old roundId is rejected as stale', () => {
  const room = createRoom(NOW);
  const { room: result } = act(room, host, request(room, 'award', { points: 1 }), NOW);
  const { room: nextRound } = act(result, host, request(result, 'next'), NOW);

  const stale = { action: 'submit', text: 'late', id: 'late_request_1', stage: 'collecting', roundId: 0 };

  assert.equal(nextRound.roundId, 1);
  assert.throws(() => act(nextRound, player(7), stale, NOW), status(409));
});

test('the same id from a different viewer is a different request', () => {
  const room = createRoom(NOW);
  const shared = { action: 'submit', id: 'shared_request_id', stage: 'collecting', roundId: 0 };

  const a = act(room, player(1), { ...shared, text: 'from one' }, NOW);
  const b = act(a.room, player(2), { ...shared, text: 'from two' }, NOW);

  assert.equal(b.replayed, false);
  assert.equal(b.room.submission, 'from two');
});

test('a rejected request is not recorded, so retrying it is rejected again', () => {
  const room = createRoom(NOW);
  const bad = { action: 'award', points: 99, id: 'bad_points_001', stage: 'collecting', roundId: 0 };

  assert.throws(() => act(room, host, bad, NOW), status(400));
  assert.throws(() => act(room, host, bad, NOW), status(400));
  assert.equal(room.handled.size, 0);
});

test('a dropped reply cannot double-score, whether the retry reuses the id or not', () => {
  const room = createRoom(NOW);
  const req = request(room, 'award', { points: 3 });
  const { room: applied } = act(room, host, req, NOW);

  // The client never saw the reply. It retries once with the same id, once with a new one.
  const sameId = act(applied, host, req, NOW + 5000);
  const newId = () => act(applied, host, { ...req, id: 'fresh_retry_id_1' }, NOW + 6000);

  assert.equal(sameId.room.score, 3);
  assert.throws(newId, status(409));
});

test('public viewers cannot act, and players cannot use host actions', () => {
  const room = createRoom(NOW);

  assert.throws(() => act(room, board, request(room, 'award', { points: 1 }), NOW), status(403));
  assert.throws(() => act(room, player(3), request(room, 'award', { points: 1 }), NOW), status(403));
  assert.throws(() => act(room, host, request(room, 'submit', { text: 'x' }), NOW), status(403));
});

test('request ids must match the allowed format', () => {
  const room = createRoom(NOW);
  const base = { action: 'close', stage: room.stage, roundId: room.roundId };

  for (const id of [undefined, '', 'short', 'has space in it', 'x'.repeat(81)]) {
    assert.throws(() => act(room, host, { ...base, id }, NOW), status(400), String(id));
  }
});

test('actions in the wrong stage are rejected', () => {
  const room = createRoom(NOW);

  assert.throws(() => act(room, host, request(room, 'next'), NOW), status(409));
});

test('a closed room accepts nothing', () => {
  const room = createRoom(NOW);
  const { room: closed } = act(room, host, request(room, 'close'), NOW);

  assert.throws(() => act(closed, host, request(closed, 'close'), NOW), status(410));
});

test('the processed-request log is capped and forgets the oldest id first', () => {
  let room = createRoom(NOW);
  const first = { action: 'submit', text: 'first', id: 'cap_request_0000', stage: 'collecting', roundId: 0 };
  room = act(room, player(1), first, NOW).room;
  for (let i = 1; i < HANDLED_LIMIT; i++) {
    room = act(room, player(1), { ...first, id: `cap_request_${i}`, text: `t${i}` }, NOW).room;
  }
  assert.equal(room.handled.size, HANDLED_LIMIT);

  room = act(room, player(1), { ...first, id: 'cap_request_over', text: 'over' }, NOW).room;

  assert.equal(room.handled.size, HANDLED_LIMIT);
  // The window is bounded: the first id is no longer recognised as a replay.
  assert.equal(act(room, player(1), first, NOW).replayed, false);
});

test('act returns a new room and leaves the previous one untouched', () => {
  const room = Object.freeze(createRoom(NOW));
  const before = { revision: room.revision, handled: room.handled.size };

  const { room: after } = act(room, host, request(room, 'award', { points: 2 }), NOW + 1);

  assert.notEqual(after, room);
  assert.deepEqual({ revision: room.revision, handled: room.handled.size }, before);
});
