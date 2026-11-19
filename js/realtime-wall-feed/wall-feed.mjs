// One read-only connection feeds the page. HTTP is only a degraded-mode fallback.
// The browser pieces (WebSocket, fetch, timers, tab visibility, online state) are passed
// in as `env`, so the connection logic can be driven by fakes in tests.

export const STATUS = Object.freeze({
  OK: '',
  RECONNECTING: 'reconnecting',
  DISCONNECTED: 'disconnected',
  OFFLINE: 'offline',
});

export const SOCKET_OPEN = 1;
const HANDSHAKE_TIMEOUT_MS = 8000;
const FETCH_TIMEOUT_MS = 8000;
const HEARTBEAT_INTERVAL_MS = 45_000;
const PONG_TIMEOUT_MS = 15_000;
const FIRST_FALLBACK_DELAY_MS = 4000;
const FALLBACK_BASE_MS = 30_000;
const FALLBACK_MAX_MS = 120_000;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 60_000;
const RECONNECT_EXPONENT_CAP = 6;
const RECONNECT_JITTER = 0.2;
const PING_MESSAGE = 'keepalive';
const PONG_MESSAGE = 'alive';

/** Exponential delay, capped, plus 0 to 20 percent jitter so clients do not reconnect in lockstep. */
export function reconnectDelay(failures, random = Math.random) {
  const base = Math.min(RECONNECT_BASE_MS * 2 ** Math.min(failures, RECONNECT_EXPONENT_CAP), RECONNECT_MAX_MS);
  return base + random() * base * RECONNECT_JITTER;
}

/** A snapshot is applied only if it is well formed and not older than what is on screen. */
export function isAcceptableSnapshot(data, currentRevision) {
  return Boolean(data)
    && data.type === 'wall'
    && Number.isInteger(data.revision)
    && data.revision >= currentRevision
    && Array.isArray(data.notes);
}

/** http(s) page address to ws(s) socket address. */
export function socketUrlFor(path, pageHref) {
  const url = new URL(path, pageHref);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url;
}

export function browserEnv() {
  return {
    createSocket: path => new WebSocket(socketUrlFor(path, location.href)),
    fetch: (path, init) => fetch(path, init),
    setTimeout: (fn, delay) => setTimeout(fn, delay),
    clearTimeout: id => clearTimeout(id),
    setInterval: (fn, delay) => setInterval(fn, delay),
    clearInterval: id => clearInterval(id),
    random: Math.random,
    page: {
      isHidden: () => document.hidden,
      isOnline: () => navigator.onLine,
      subscribe({ onVisibilityChange, onOnline, onOffline }) {
        document.addEventListener('visibilitychange', onVisibilityChange);
        window.addEventListener('online', onOnline);
        window.addEventListener('offline', onOffline);
        return () => {
          document.removeEventListener('visibilitychange', onVisibilityChange);
          window.removeEventListener('online', onOnline);
          window.removeEventListener('offline', onOffline);
        };
      },
    },
  };
}

/**
 * Start the feed. `onChange(snapshot)` receives every accepted snapshot;
 * `onStatus(STATUS.*)` reports connection trouble. Returns { close() }.
 */
export function connectWallFeed({
  onChange, onStatus = () => {},
  socketPath = '/api/wall/socket', fallbackPath = '/api/wall',
  env = browserEnv(),
}) {
  const { page, setTimeout, clearTimeout, setInterval, clearInterval } = env;
  let socket, retryTimer, handshakeTimer, heartbeatTimer, pongTimer, fallbackTimer, request;
  let stopped = false, received = false, failures = 0, fallbackDelay = FALLBACK_BASE_MS;
  let revision = -1;

  const available = () => !stopped && !page.isHidden() && page.isOnline();
  const healthy = () => socket?.readyState === SOCKET_OPEN && received;

  function accept(data) {
    if (!isAcceptableSnapshot(data, revision)) return false;
    revision = data.revision;
    onChange(data);
    onStatus(STATUS.OK);
    return true;
  }

  function scheduleFallback(delay) {
    if (!available() || healthy() || fallbackTimer || request) return;
    fallbackTimer = setTimeout(() => { fallbackTimer = null; refresh(); }, delay);
  }

  // Slow HTTP polling, used only while the socket is not delivering.
  async function refresh() {
    if (!available() || healthy() || request) return;
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await env.fetch(fallbackPath, { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error('snapshot unavailable');
      const data = await response.json();
      if (!controller.signal.aborted && available() && !healthy()) {
        if (!accept(data)) throw new Error('invalid snapshot');
        fallbackDelay = FALLBACK_BASE_MS;
      }
    } catch {
      if (request === controller && !healthy()) {
        fallbackDelay = Math.min(fallbackDelay * 2, FALLBACK_MAX_MS);
        onStatus(STATUS.DISCONNECTED);
      }
    } finally {
      clearTimeout(timeout);
      if (request === controller) { request = null; scheduleFallback(fallbackDelay); }
    }
  }

  function clearSocketTimers() {
    clearTimeout(handshakeTimer);
    clearTimeout(pongTimer);
    clearInterval(heartbeatTimer);
  }

  function reconnect() {
    if (!available() || retryTimer) return;
    retryTimer = setTimeout(() => { retryTimer = null; connect(); }, reconnectDelay(failures++, env.random));
    scheduleFallback(0);
  }

  function connect() {
    if (!available() || socket) return;
    let connection;
    try {
      connection = env.createSocket(socketPath);
    } catch {
      reconnect();
      return;
    }
    socket = connection;
    received = false;

    const fail = () => {
      if (socket !== connection) return;   // an old socket cannot disturb the current one
      socket = null;
      clearSocketTimers();
      connection.close();
      onStatus(STATUS.RECONNECTING);
      reconnect();
    };
    handshakeTimer = setTimeout(fail, HANDSHAKE_TIMEOUT_MS);
    connection.onmessage = ({ data }) => {
      if (socket !== connection) return;
      if (data === PONG_MESSAGE) { clearTimeout(pongTimer); return; }
      let packet;
      try { packet = JSON.parse(data); } catch { return; }
      if (!accept(packet)) return;
      if (!received) {
        received = true;
        clearTimeout(handshakeTimer);
        clearTimeout(fallbackTimer);
        fallbackTimer = null;
        request?.abort();
        // A fixed message the platform answers without waking the database.
        heartbeatTimer = setInterval(() => {
          if (connection.readyState !== SOCKET_OPEN) { fail(); return; }
          connection.send(PING_MESSAGE);
          pongTimer = setTimeout(fail, PONG_TIMEOUT_MS);
        }, HEARTBEAT_INTERVAL_MS);
      }
      failures = 0;
      fallbackDelay = FALLBACK_BASE_MS;
    };
    connection.onclose = fail;
    connection.onerror = fail;
    scheduleFallback(FIRST_FALLBACK_DELAY_MS);
  }

  // Hidden tab or no network: stop everything, keep nothing running.
  function suspend() {
    clearTimeout(retryTimer);
    retryTimer = null;
    clearTimeout(fallbackTimer);
    fallbackTimer = null;
    clearSocketTimers();
    request?.abort();
    request = null;
    const previous = socket;
    socket = null;
    previous?.close();
  }

  function resume() {
    if (available()) {
      connect();
      return;
    }
    suspend();
    if (!page.isOnline()) onStatus(STATUS.OFFLINE);
  }

  const goOffline = () => {
    suspend();
    onStatus(STATUS.OFFLINE);
  };

  const unsubscribe = page.subscribe({
    onVisibilityChange: resume, onOnline: resume, onOffline: goOffline,
  });
  connect();

  return {
    close() {
      stopped = true;
      suspend();
      unsubscribe();
    },
  };
}
