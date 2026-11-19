import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CLOSED_LINGER_MS,
  PRESENCE_GRACE_MS,
  nextAlarmAt,
  planAlarm,
  planBroadcast,
} from './broadcast-plan.mjs';

const NOW = 1_000_000;
const idle = { now: NOW, closed: false, timersRunning: false, deadline: null, nextRoundAt: null,
  touchedAt: NOW - 1000, expiresAt: NOW + 3_600_000, unauthDeadlines: [], absentSeenAt: [] };
const alarm = overrides => nextAlarmAt({ ...idle, ...overrides });

const sessions = () => [
  { id: 'a', authenticated: true, revision: 4 },
  { id: 'b', authenticated: true, revision: 3 },
  { id: 'c', authenticated: true, revision: -1 },
  { id: 'd', authenticated: false, revision: -1 },
];

test('sends only to authenticated sockets whose saved revision differs', () => {
  const { sendTo } = planBroadcast(sessions(), 4);

  assert.deepEqual(sendTo, ['b', 'c']);
});

test('records the delivered revision, so the same revision is never pushed twice', () => {
  const first = planBroadcast(sessions(), 4);
  const second = planBroadcast(first.sessions, 4);

  assert.deepEqual(second.sendTo, []);
  assert.equal(first.sessions.find(s => s.id === 'c').revision, 4);
});

test('a new revision reaches every authenticated socket again', () => {
  const settled = planBroadcast(sessions(), 4).sessions;

  assert.deepEqual(planBroadcast(settled, 5).sendTo, ['a', 'b', 'c']);
});

test('a forced socket gets the state even at the same revision', () => {
  const settled = planBroadcast(sessions(), 4).sessions;

  assert.deepEqual(planBroadcast(settled, 4, 'a').sendTo, ['a']);
});

test('a socket that has not authenticated never receives state', () => {
  const { sendTo } = planBroadcast(sessions(), 4, 'd');

  assert.ok(!sendTo.includes('d'));
});

test('planBroadcast does not mutate its input', () => {
  const input = Object.freeze(sessions().map(s => Object.freeze(s)));

  assert.doesNotThrow(() => planBroadcast(input, 9, 'a'));
});

test('waiting 90 seconds at an unchanged revision produces no state pushes', () => {
  // Models the idle-wait principle. The measured run is described in the README.
  let current = planBroadcast(sessions(), 4).sessions;
  let pushes = 0;
  for (let second = 0; second < 90; second++) {
    const tick = planBroadcast(current, 4);
    pushes += tick.sendTo.length;
    current = tick.sessions;
  }

  assert.equal(pushes, 0);
});

test('alarm picks the earliest of game deadline, auth deadline, grace and expiry', () => {
  const running = { timersRunning: true, deadline: NOW + 50_000 };

  assert.equal(alarm(running), NOW + 50_000);
  assert.equal(alarm({ ...running, unauthDeadlines: [NOW + 8_000, NOW + 9_000] }), NOW + 8_000);
  assert.equal(alarm({ ...running, absentSeenAt: [NOW - 5_000] }), NOW - 5_000 + PRESENCE_GRACE_MS);
  assert.equal(alarm({ ...running, expiresAt: NOW + 20_000 }), NOW + 20_000);
});

test('with no timers running, the room expiry is the only game-side alarm', () => {
  assert.equal(alarm({ deadline: NOW + 5_000 }), idle.expiresAt);
});

test('the next-round time counts only while timers are running', () => {
  assert.equal(alarm({ timersRunning: true, nextRoundAt: NOW + 2_000 }), NOW + 2_000);
  assert.equal(alarm({ timersRunning: false, nextRoundAt: NOW + 2_000 }), idle.expiresAt);
});

test('authenticated sockets carry no auth deadline, so they add no alarm', () => {
  assert.equal(alarm({ unauthDeadlines: [] }), idle.expiresAt);
});

test('grace for absent players already past is ignored', () => {
  assert.equal(alarm({ absentSeenAt: [NOW - PRESENCE_GRACE_MS - 1] }), idle.expiresAt);
});

test('a closed room is cleaned up after a linger period, not at expiry or game deadline', () => {
  const closed = alarm({ closed: true, touchedAt: NOW - 10_000, timersRunning: true, deadline: NOW + 1_000 });

  assert.equal(closed, NOW - 10_000 + CLOSED_LINGER_MS);
});

test('the alarm is never earlier than one millisecond from now', () => {
  assert.equal(alarm({ timersRunning: true, deadline: NOW - 60_000 }), NOW + 1);
});

test('returns null when there is nothing to wake for', () => {
  assert.equal(alarm({ expiresAt: Infinity }), null);
});

test('planAlarm skips the storage write when the alarm is unchanged', () => {
  const at = nextAlarmAt(idle);

  assert.deepEqual(planAlarm(at, idle), { at, shouldSet: false });
  assert.deepEqual(planAlarm(undefined, idle), { at, shouldSet: true });
  assert.equal(planAlarm(5, { ...idle, expiresAt: Infinity }).shouldSet, false);
});
