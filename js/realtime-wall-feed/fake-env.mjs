// Test doubles for wall-feed.mjs: fake timers, fake WebSocket, fake fetch, fake page.
// Nothing here touches the network or real time.

export const flush = () => new Promise(resolve => setImmediate(resolve));

export function createClock() {
  let now = 0;
  let nextId = 0;
  const timers = new Map();

  function tick(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...timers].sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!next || next[1].at > end) break;
      const [id, timer] = next;
      now = timer.at;
      if (timer.every) timer.at += timer.every;
      else timers.delete(id);
      timer.fn();
    }
    now = end;
  }

  return {
    now: () => now,
    tick,
    pendingTimers: () => timers.size,
    setTimeout(fn, delay = 0) { timers.set(++nextId, { fn, at: now + delay }); return nextId; },
    clearTimeout(id) { timers.delete(id); },
    setInterval(fn, every) { timers.set(++nextId, { fn, at: now + every, every }); return nextId; },
    clearInterval(id) { timers.delete(id); },
  };
}

class FakeSocket {
  constructor(path) {
    this.path = path;
    this.readyState = 0;
    this.sent = [];
  }
  open() { this.readyState = 1; }
  send(data) { this.sent.push(data); }
  receive(data) { this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) }); }
  // Closing calls onclose synchronously, which is stricter than a browser: the feed
  // must ignore the close event of a socket it already dropped.
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.();
  }
}

export function createPage({ hidden = false, online = true } = {}) {
  const page = {
    hidden, online, listeners: null,
    isHidden: () => page.hidden,
    isOnline: () => page.online,
    subscribe(listeners) {
      page.listeners = listeners;
      return () => { page.listeners = null; };
    },
    setHidden(value) { page.hidden = value; page.listeners?.onVisibilityChange(); },
    goOffline() { page.online = false; page.listeners?.onOffline(); },
    goOnline() { page.online = true; page.listeners?.onOnline(); },
  };
  return page;
}

export function createEnv({ hidden = false, online = true, random = () => 0 } = {}) {
  const clock = createClock();
  const page = createPage({ hidden, online });
  const sockets = [];
  const fetches = [];
  const behavior = { createSocketFailures: 0 };

  const env = {
    page, random,
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
    setInterval: clock.setInterval, clearInterval: clock.clearInterval,
    createSocket(path) {
      if (behavior.createSocketFailures > 0) {
        behavior.createSocketFailures--;
        throw new Error('socket constructor failed');
      }
      const socket = new FakeSocket(path);
      sockets.push(socket);
      return socket;
    },
    fetch(path, init) {
      return new Promise((resolve, reject) => {
        const entry = { path, init, at: clock.now() };
        entry.respond = (data, ok = true) => resolve({ ok, json: async () => data });
        init.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
        fetches.push(entry);
      });
    },
  };
  return { env, clock, page, sockets, fetches, behavior };
}

export const snapshot = (revision, extra = {}) => ({ type: 'wall', revision, notes: [], ...extra });
