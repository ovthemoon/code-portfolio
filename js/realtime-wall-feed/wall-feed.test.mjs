import test from 'node:test';
import assert from 'node:assert/strict';
import {
  STATUS, connectWallFeed, isAcceptableSnapshot, reconnectDelay, socketUrlFor,
} from './wall-feed.mjs';
import { createEnv, flush, snapshot } from './fake-env.mjs';

function start(options) {
  const world = createEnv(options);
  const changes = [];
  const statuses = [];
  const feed = connectWallFeed({
    env: world.env,
    onChange: data => changes.push(data.revision),
    onStatus: status => statuses.push(status),
  });
  return { ...world, feed, changes, statuses };
}

// Let time pass on a healthy socket, answering every keepalive like the server does.
function idle(socket, clock, ms) {
  for (let elapsed = 0; elapsed < ms; elapsed += 45_000) {
    clock.tick(45_000);
    socket.receive('alive');
  }
}

// A socket that has connected and delivered its first snapshot.
function healthy(options) {
  const world = start(options);
  const socket = world.sockets[0];
  socket.open();
  socket.receive(snapshot(1));
  return { ...world, socket };
}

test('reconnect delay doubles up to a cap, with 0 to 20 percent jitter on top', () => {
  const delays = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(failures => reconnectDelay(failures, () => 0));

  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 16000, 32000, 60000, 60000, 60000]);
  assert.equal(reconnectDelay(0, () => 1), 1200);
  assert.ok(reconnectDelay(7, () => 0.999) <= 72_000);
});

test('a snapshot is accepted when well formed and not older than the current revision', () => {
  const ok = snapshot(5);

  assert.equal(isAcceptableSnapshot(ok, 5), true);
  assert.equal(isAcceptableSnapshot(ok, 4), true);
  assert.equal(isAcceptableSnapshot(ok, 6), false);
  for (const bad of [null, undefined, {}, snapshot('5'), snapshot(5.5), { type: 'other', revision: 9, notes: [] },
    { type: 'wall', revision: 9 }, { type: 'wall', revision: 9, notes: 'x' }]) {
    assert.equal(isAcceptableSnapshot(bad, -1), false, JSON.stringify(bad));
  }
});

test('the socket address follows the page protocol', () => {
  assert.equal(socketUrlFor('/api/wall/socket', 'https://site.test/wall.html?x=1').href, 'wss://site.test/api/wall/socket');
  assert.equal(socketUrlFor('/api/wall/socket', 'http://localhost:8080/').href, 'ws://localhost:8080/api/wall/socket');
});

test('pushed snapshots are applied in order, and older or malformed ones are ignored', () => {
  const { socket, changes, statuses } = healthy();

  socket.receive(snapshot(3));
  socket.receive(snapshot(2));
  socket.receive('not json');
  socket.receive({ type: 'other' });
  socket.receive(snapshot(4));

  assert.deepEqual(changes, [1, 3, 4]);
  assert.equal(statuses.at(-1), STATUS.OK);
});

test('after the first snapshot it pings every 45 seconds and stays while replies arrive', () => {
  const { socket, sockets, clock } = healthy();

  clock.tick(45_000);
  socket.receive('alive');
  clock.tick(45_000);

  assert.deepEqual(socket.sent, ['keepalive', 'keepalive']);
  assert.equal(sockets.length, 1);
});

test('a missing reply drops the socket, reconnects, and asks over HTTP meanwhile', () => {
  const { socket, sockets, fetches, statuses, clock } = healthy();
  clock.tick(45_000);

  clock.tick(15_000);

  assert.equal(socket.readyState, 3);
  assert.equal(statuses.at(-1), STATUS.RECONNECTING);
  clock.tick(0);
  assert.equal(fetches.length, 1, 'HTTP fallback starts at once');
  clock.tick(999);
  assert.equal(sockets.length, 1);
  clock.tick(1);
  assert.equal(sockets.length, 2);
});

test('if the first snapshot does not arrive, HTTP answers after 4 seconds and the socket is dropped after 8', async () => {
  const { sockets, fetches, changes, statuses, clock } = start();

  clock.tick(3999);
  assert.equal(fetches.length, 0);
  clock.tick(1);
  assert.equal(fetches.length, 1);
  assert.equal(fetches[0].path, '/api/wall');
  fetches[0].respond(snapshot(1));
  await flush();
  assert.deepEqual(changes, [1]);

  clock.tick(4000);

  assert.equal(sockets[0].readyState, 3);
  assert.equal(statuses.at(-1), STATUS.RECONNECTING);
  clock.tick(1000);
  assert.equal(sockets.length, 2);
});

test('HTTP polling after success waits 30 seconds', async () => {
  const { fetches, clock } = start();
  clock.tick(4000);
  fetches[0].respond(snapshot(1));
  await flush();

  clock.tick(29_999);
  assert.equal(fetches.length, 1);
  clock.tick(1);

  assert.equal(fetches.length, 2);
});

test('HTTP failures back off 60 seconds, then 120 seconds, and stay there', async () => {
  const { fetches, statuses, clock } = start();
  const failLatest = async () => { fetches.at(-1).respond(null, false); await flush(); };

  clock.tick(4000);
  await failLatest();
  assert.equal(statuses.at(-1), STATUS.DISCONNECTED);
  clock.tick(59_999);
  assert.equal(fetches.length, 1);
  clock.tick(1);
  assert.equal(fetches.length, 2);

  await failLatest();
  clock.tick(119_999);
  assert.equal(fetches.length, 2);
  clock.tick(1);
  assert.equal(fetches.length, 3);

  await failLatest();
  clock.tick(120_000);
  assert.equal(fetches.length, 4, 'capped at 120 seconds');
});

test('a stale HTTP snapshot counts as a failure', async () => {
  const { fetches, changes, statuses, clock } = start();
  clock.tick(4000);
  fetches[0].respond(snapshot(5));
  await flush();
  clock.tick(30_000);

  fetches[1].respond(snapshot(4));
  await flush();

  assert.deepEqual(changes, [5]);
  assert.equal(statuses.at(-1), STATUS.DISCONNECTED);
});

test('a healthy socket cancels the pending HTTP request and the fallback timer', async () => {
  const world = start();
  world.clock.tick(4000);
  const [pending] = world.fetches;
  const socket = world.sockets[0];
  socket.open();

  socket.receive(snapshot(1));
  await flush();

  assert.equal(pending.init.signal.aborted, true);
  idle(socket, world.clock, 600_000);
  assert.equal(world.fetches.length, 1);
  assert.equal(world.sockets.length, 1);
});

test('a socket that is healthy in time means HTTP is never used', () => {
  const { fetches, socket, sockets, clock } = healthy();

  idle(socket, clock, 600_000);

  assert.equal(fetches.length, 0);
  assert.equal(sockets.length, 1);
});

test('the reconnect delay starts over after a snapshot arrives', () => {
  const { sockets, clock } = start();

  sockets[0].close();
  clock.tick(999);
  assert.equal(sockets.length, 1);
  clock.tick(1);
  assert.equal(sockets.length, 2);

  sockets[1].close();
  clock.tick(1999);
  assert.equal(sockets.length, 2);
  clock.tick(1);
  assert.equal(sockets.length, 3);

  sockets[2].open();
  sockets[2].receive(snapshot(1));
  sockets[2].close();
  clock.tick(999);
  assert.equal(sockets.length, 3);
  clock.tick(1);
  assert.equal(sockets.length, 4, 'back to the first step');
});

test('jitter stretches the delay by up to 20 percent', () => {
  const { sockets, clock } = start({ random: () => 1 });

  sockets[0].close();
  clock.tick(1199);
  assert.equal(sockets.length, 1);
  clock.tick(1);

  assert.equal(sockets.length, 2);
});

test('a socket constructor that throws is handled as a failed attempt', () => {
  const world = createEnv();
  world.behavior.createSocketFailures = 1;

  connectWallFeed({ env: world.env, onChange() {} });
  assert.equal(world.sockets.length, 0);
  world.clock.tick(1000);

  assert.equal(world.sockets.length, 1);
});

test('hiding the tab closes the socket and silences everything; showing it reconnects', () => {
  const { socket, sockets, fetches, page, clock } = healthy();

  page.setHidden(true);

  assert.equal(socket.readyState, 3);
  clock.tick(600_000);
  assert.equal(sockets.length, 1);
  assert.equal(fetches.length, 0);
  assert.equal(clock.pendingTimers(), 0);
  page.setHidden(false);
  assert.equal(sockets.length, 2);
});

test('hiding the tab aborts a pending HTTP request', () => {
  const { fetches, page, clock } = start();
  clock.tick(4000);

  page.setHidden(true);

  assert.equal(fetches[0].init.signal.aborted, true);
  clock.tick(600_000);
  assert.equal(fetches.length, 1);
});

test('a page opened in a hidden tab connects only when it becomes visible', () => {
  const { sockets, fetches, page, clock } = start({ hidden: true });

  clock.tick(600_000);
  assert.equal(sockets.length, 0);
  assert.equal(fetches.length, 0);
  page.setHidden(false);

  assert.equal(sockets.length, 1);
});

test('going offline suspends and reports; coming back online reconnects', () => {
  const { socket, sockets, statuses, page, clock } = healthy();

  page.goOffline();

  assert.equal(statuses.at(-1), STATUS.OFFLINE);
  assert.equal(socket.readyState, 3);
  clock.tick(600_000);
  assert.equal(sockets.length, 1);
  page.goOnline();
  assert.equal(sockets.length, 2);
});

test('close stops the feed for good and removes the page listeners', () => {
  const { feed, socket, sockets, fetches, page, clock } = healthy();
  const listeners = page.listeners;

  feed.close();
  listeners.onOnline();
  listeners.onVisibilityChange();

  assert.equal(page.listeners, null);
  assert.equal(socket.readyState, 3);
  clock.tick(600_000);
  assert.equal(sockets.length, 1);
  assert.equal(fetches.length, 0);
});
