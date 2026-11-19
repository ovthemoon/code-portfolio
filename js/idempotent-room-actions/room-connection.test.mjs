import test from 'node:test';
import assert from 'node:assert/strict';
import { ACTION_TIMEOUT_MS, MAX_ATTEMPTS, RoomConnection, backoffDelay } from './room-connection.mjs';

// Fake socket class and fake timers: no network, no real time.
function fixture({ random = () => 0.5 } = {}) {
  let now = 0;
  let timerId = 0;
  const timers = new Map();
  const sockets = [];
  const states = [];
  const statuses = [];
  const fatal = [];

  class FakeSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.bufferedAmount = 0;
      this.sent = [];
      sockets.push(this);
    }
    open() { this.readyState = 1; this.onopen(); }
    send(data) { this.sent.push(data); }
    message(data) { this.onmessage({ data: JSON.stringify(data) }); }
    close(code = 1006) { this.readyState = 3; this.onclose?.({ code, reason: '' }); }
  }

  const connection = new RoomConnection({
    url: 'ws://room.test/socket', token: 'secret', WebSocketImpl: FakeSocket, random,
    onState: state => states.push(state),
    onStatus: (...status) => statuses.push(status),
    onFatal: error => fatal.push(error),
    setTimer: (fn, delay) => { timers.set(++timerId, { fn, at: now + delay }); return timerId; },
    clearTimer: id => timers.delete(id),
  });

  function tick(ms) {
    const end = now + ms;
    for (;;) {
      const [id, timer] = [...timers].sort((a, b) => a[1].at - b[1].at)[0] ?? [];
      if (!timer || timer.at > end) break;
      now = timer.at;
      timers.delete(id);
      timer.fn();
    }
    now = end;
  }

  function ready(stage = 'lobby') {
    connection.start();
    const socket = sockets.at(-1);
    socket.open();
    socket.message({ type: 'state', state: { stage, revision: 1 } });
    return socket;
  }

  return { connection, sockets, states, statuses, fatal, tick, ready };
}

const body = (id, extra = {}) => ({ id, action: 'award', stage: 'collecting', roundId: 0, ...extra });

test('sends hello with the token in the message, not in the URL', () => {
  const f = fixture();
  const socket = f.ready();

  assert.deepEqual(JSON.parse(socket.sent[0]), { type: 'hello', protocol: 1, token: 'secret' });
  assert.equal(socket.url.includes('secret'), false);
});

test('a reply resolves its request, and an error reply rejects with the status', async () => {
  const f = fixture();
  const socket = f.ready();

  const ok = f.connection.action(body('request_aaa1'));
  socket.message({ type: 'reply', id: 'request_aaa1', status: 200, data: { stage: 'result' } });
  assert.deepEqual(await ok, { stage: 'result' });

  const stale = f.connection.action(body('request_aaa2'));
  socket.message({ type: 'reply', id: 'request_aaa2', status: 409, data: { error: 'stage changed' } });
  await assert.rejects(stale, error => error.status === 409 && /stage changed/.test(error.message));
});

test('replies are matched by id even when they arrive out of order', async () => {
  const f = fixture();
  const socket = f.ready();

  const first = f.connection.action(body('request_bbb1'));
  const second = f.connection.action(body('request_bbb2'));
  socket.message({ type: 'reply', id: 'request_bbb2', status: 200, data: { n: 2 } });
  socket.message({ type: 'reply', id: 'request_bbb1', status: 200, data: { n: 1 } });

  assert.deepEqual(await first, { n: 1 });
  assert.deepEqual(await second, { n: 2 });
});

test('a lost connection rejects pending requests and never replays them', async () => {
  const f = fixture();
  const socket = f.ready();
  const pending = f.connection.action(body('request_ccc1'));

  socket.close();
  await assert.rejects(pending, /connection lost/);

  f.tick(1200);
  const restored = f.sockets.at(-1);
  restored.open();
  restored.message({ type: 'state', state: { stage: 'result', revision: 2 } });

  assert.notEqual(restored, socket);
  assert.equal(restored.sent.length, 1, 'only the hello is sent after reconnecting');
});

test('an unanswered request times out, rejects, and drops the connection', async () => {
  const f = fixture();
  const socket = f.ready();
  const pending = f.connection.action(body('request_ddd1'));

  f.tick(ACTION_TIMEOUT_MS);

  await assert.rejects(pending, /no response/);
  assert.equal(socket.readyState, 3);
  f.tick(1200);
  assert.equal(f.sockets.length, 2, 'a reconnect was scheduled');
});

test('an answered request does not time out later', async () => {
  const f = fixture();
  const socket = f.ready();
  const pending = f.connection.action(body('request_eee1'));
  socket.message({ type: 'reply', id: 'request_eee1', status: 200, data: {} });
  await pending;

  f.tick(ACTION_TIMEOUT_MS * 3);

  assert.equal(socket.readyState, 1);
  assert.equal(f.sockets.length, 1);
});

test('actions are refused while not connected', async () => {
  const f = fixture();

  await assert.rejects(f.connection.action(body('request_fff1')), /not connected/);
});

test('actions are refused when too much data is still queued', async () => {
  const f = fixture();
  const socket = f.ready();
  socket.bufferedAmount = 5_000_000;

  await assert.rejects(f.connection.action(body('request_fff2')), /busy/);
});

test('backoff doubles each attempt, is capped, and jitters within 20 percent', () => {
  const delays = [0, 1, 2, 3, 4, 5, 6, 7].map(attempt => backoffDelay(attempt, () => 0.5));

  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]);
  assert.ok(Math.abs(backoffDelay(2, () => 0) - 3200) < 1e-6);
  assert.ok(Math.abs(backoffDelay(2, () => 1) - 4800) < 1e-6);
});

test('reconnects use the backoff schedule, then stop after the attempt limit', () => {
  const f = fixture();
  f.connection.start();

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const count = f.sockets.length;
    const delay = backoffDelay(attempt, () => 0.5);
    f.sockets.at(-1).close();
    f.tick(delay - 1);
    assert.equal(f.sockets.length, count, `attempt ${attempt} waits`);
    f.tick(1);
    assert.equal(f.sockets.length, count + 1, `attempt ${attempt} reconnects`);
  }
  f.sockets.at(-1).close();
  f.tick(600_000);

  assert.equal(f.sockets.length, MAX_ATTEMPTS + 1);
  assert.deepEqual(f.statuses.at(-1), [false, true]);
});

test('resume starts over after giving up', () => {
  const f = fixture();
  f.connection.start();
  for (let i = 0; i <= MAX_ATTEMPTS; i++) { f.sockets.at(-1).close(); f.tick(60_000); }
  const count = f.sockets.length;

  f.connection.resume();

  assert.equal(f.sockets.length, count + 1);
});

test('a received state resets the attempt counter', () => {
  const f = fixture();
  f.connection.start();
  f.sockets.at(-1).close();
  f.tick(1200);
  f.sockets.at(-1).close();
  f.tick(2400);

  const socket = f.sockets.at(-1);
  socket.open();
  socket.message({ type: 'state', state: { stage: 'lobby', revision: 1 } });
  const count = f.sockets.length;
  socket.close();
  f.tick(999);
  assert.equal(f.sockets.length, count);
  f.tick(1);

  assert.equal(f.sockets.length, count + 1, 'the delay is back to the first step');
});

test('a terminal close code stops retries and reports it', () => {
  const f = fixture();
  f.connection.start();
  f.sockets.at(-1).close(4001);
  f.tick(600_000);

  assert.equal(f.sockets.length, 1);
  assert.equal(f.fatal[0].status, 401);
});

test('state messages from an old socket are ignored', () => {
  const f = fixture();
  const old = f.ready();
  old.close();
  f.tick(1200);
  const current = f.sockets.at(-1);
  current.open();
  current.message({ type: 'state', state: { stage: 'result', revision: 2 } });

  old.message({ type: 'state', state: { stage: 'lobby', revision: 99 } });

  assert.equal(f.states.at(-1).stage, 'result');
});
