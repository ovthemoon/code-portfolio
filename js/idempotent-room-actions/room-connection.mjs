// One room connection from the client side. No polling fallback, and no automatic
// replay of actions: a request that was in flight when the socket dropped is rejected,
// and the caller decides whether to ask again.
// Left out of this excerpt: heartbeat, tab visibility and online/offline handling.

export const ACTION_TIMEOUT_MS = 10_000;
export const CONNECT_TIMEOUT_MS = 10_000;
export const MAX_ATTEMPTS = 8;
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;
const JITTER_MIN = 0.8;
const JITTER_SPREAD = 0.4;
const BUFFERED_BYTES_LIMIT = 2_000_000;
const CLOSE_CODE_CREDENTIALS = 4001;
const CLOSE_CODE_EXPIRED = 4004;

/** Exponential backoff, capped, multiplied by a jitter factor in [0.8, 1.2). */
export function backoffDelay(attempt, random = Math.random) {
  return Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** attempt) * (JITTER_MIN + JITTER_SPREAD * random());
}

export class RoomConnection {
  constructor({
    url, token, onState, onStatus, onFatal,
    WebSocketImpl = globalThis.WebSocket,
    setTimer = (fn, delay) => globalThis.setTimeout(fn, delay),
    clearTimer = id => globalThis.clearTimeout(id),
    random = Math.random,
  }) {
    Object.assign(this, { url, token, onState, onStatus, onFatal, WebSocketImpl, setTimer, clearTimer, random });
    this.pending = new Map();
    this.attempts = 0;
    this.ready = false;
    this.stopped = false;
    this.socket = null;
    this.retryTimer = null;
    this.connectTimer = null;
  }

  start() {
    if (this.stopped || this.socket || this.retryTimer) return;
    this.connect();
  }

  connect() {
    let socket;
    try {
      socket = new this.WebSocketImpl(this.url);
    } catch {
      this.retry();
      return;
    }
    this.socket = socket;
    this.ready = false;
    this.onStatus(false);
    this.connectTimer = this.setTimer(() => this.disconnect(), CONNECT_TIMEOUT_MS);

    // Every handler checks `this.socket === socket` so a stale socket cannot act.
    socket.onopen = () => {
      if (this.socket === socket) socket.send(JSON.stringify({ type: 'hello', protocol: 1, token: this.token }));
    };
    socket.onmessage = event => {
      if (this.socket !== socket) return;
      let message;
      try { message = JSON.parse(event.data); } catch { this.disconnect(); return; }
      this.handle(message);
    };
    socket.onclose = event => {
      if (this.socket !== socket) return;
      this.clearConnection();
      if ([CLOSE_CODE_CREDENTIALS, CLOSE_CODE_EXPIRED].includes(event.code)) {
        this.fail(event.code === CLOSE_CODE_CREDENTIALS ? 401 : 410, event.reason);
        return;
      }
      this.retry();
    };
    socket.onerror = () => { if (this.socket === socket) this.disconnect(); };
  }

  handle(message) {
    if (message.type === 'state') {
      this.ready = true;
      this.attempts = 0;
      this.clearTimer(this.connectTimer);
      this.onStatus(true);
      this.onState(message.state);
    } else if (message.type === 'reply') {
      const request = this.pending.get(message.id);
      if (!request) return;
      this.pending.delete(message.id);
      this.clearTimer(request.timer);
      if (message.status === 200) request.resolve(message.data);
      else request.reject(Object.assign(new Error(message.data?.error || 'request failed'), { status: message.status }));
    } else if (message.type === 'error') {
      this.fail(message.status, message.error);
    }
  }

  /** Send one action and wait for the reply with the same id. */
  action(body) {
    if (!this.ready || this.socket?.readyState !== 1) return Promise.reject(new Error('not connected'));
    if (this.socket.bufferedAmount > BUFFERED_BYTES_LIMIT) return Promise.reject(new Error('busy, try again'));
    return new Promise((resolve, reject) => {
      const timer = this.setTimer(() => {
        this.pending.delete(body.id);
        reject(new Error('no response'));
        this.disconnect();
      }, ACTION_TIMEOUT_MS);
      this.pending.set(body.id, { resolve, reject, timer });
      try {
        this.socket.send(JSON.stringify({ type: 'action', body }));
      } catch {
        this.disconnect();
      }
    });
  }

  clearConnection() {
    const socket = this.socket;
    this.socket = null;
    this.ready = false;
    this.clearTimer(this.connectTimer);
    this.connectTimer = null;
    for (const request of this.pending.values()) {
      this.clearTimer(request.timer);
      request.reject(new Error('connection lost, try again'));
    }
    this.pending.clear();
    if (socket && socket.readyState < 2) socket.close();
    if (!this.stopped) this.onStatus(false);
  }

  disconnect() {
    this.clearConnection();
    this.retry();
  }

  retry() {
    if (this.stopped || this.retryTimer) return;
    if (this.attempts >= MAX_ATTEMPTS) {
      this.onStatus(false, true);
      return;
    }
    const delay = backoffDelay(this.attempts++, this.random);
    this.retryTimer = this.setTimer(() => { this.retryTimer = null; this.start(); }, delay);
  }

  /** Called by a "reconnect" button after the attempt limit was reached. */
  resume() {
    if (this.stopped) return;
    this.attempts = 0;
    this.clearTimer(this.retryTimer);
    this.retryTimer = null;
    this.start();
  }

  fail(status, message) {
    this.stop();
    this.onFatal({ status, message });
  }

  stop() {
    this.stopped = true;
    this.clearTimer(this.retryTimer);
    this.retryTimer = null;
    this.clearConnection();
  }
}
