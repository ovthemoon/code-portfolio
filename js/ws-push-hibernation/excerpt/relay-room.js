// Excerpt. Not runnable: this is Cloudflare Durable Object code and needs the Workers runtime.
// The decisions in schedule() and broadcast() are extracted as pure functions in ../broadcast-plan.mjs.
//
// Left out: command handling, authentication messages, storage helpers, the participant
// lookup (this.viewer), and the join URL that was added to each state message.
// Names used below but defined elsewhere: response, expiry, trackOccupancy, projectRoom,
// GameError, ACTIVE, deserialize, schema, commit, snapshot, send.
import { DurableObject } from 'cloudflare:workers';

// Example values. The production values differ.
const MAX_SOCKETS_PER_ROOM = 100;
const AUTH_DEADLINE_MS = 8000;

const PRESENCE_GRACE_MS = 15000;
const CLOSED_LINGER_MS = 30 * 60 * 1000;

export class RelayRoom extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.room = null;
    this.presence = new Map();
    // The platform answers this fixed ping itself, without waking the object.
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
    ctx.blockConcurrencyWhile(async () => {
      this.schema();
      const saved = ctx.storage.sql.exec('SELECT payload FROM room_state WHERE id = 1').toArray()[0];
      if (saved) this.room = deserialize(saved.payload);
    });
  }

  sockets() {
    return this.ctx.getWebSockets().filter(ws => ws.readyState === 1);
  }

  // One alarm for everything time-based: game deadline, auth deadline, absent players, expiry.
  async schedule() {
    const previous = await this.ctx.storage.getAlarm();
    if (!this.room) return;
    const next = structuredClone(this.room);
    const occupied = this.sockets().some(ws => {
      const session = ws.deserializeAttachment();
      if (!session?.authenticated) return false;
      try { this.viewer(session.token); return true; } catch { return false; }
    });
    if (next.stage !== 'closed' && trackOccupancy(next, occupied)) this.commit(next);
    const room = this.room;
    const gameAlarm = ACTIVE.includes(room.stage) && !room.paused
      ? Math.min(
          room.deadline ?? Infinity,
          room.stage === 'question-result' ? (room.nextQuestionAt ?? Infinity) : Infinity)
      : Infinity;
    const authAlarm = Math.min(Infinity, ...this.sockets().map(ws => {
      const session = ws.deserializeAttachment();
      return session.authenticated ? Infinity : session.authDeadline;
    }));
    const graceAlarm = Math.min(
      Infinity,
      ...[...this.presence.values()].map(seenAt => seenAt + PRESENCE_GRACE_MS).filter(at => at > Date.now()));
    const at = Math.max(Date.now() + 1, Math.min(
      authAlarm,
      graceAlarm,
      room.stage === 'closed' ? room.touchedAt + CLOSED_LINGER_MS : Math.min(expiry(room), gameAlarm)));
    if (previous !== at) await this.ctx.storage.setAlarm(at);
  }

  // Send each authenticated socket its own projection, but only if the revision it
  // last received (kept in the socket attachment) differs from the current one.
  broadcast(force) {
    if (!this.room) return;
    const next = this.snapshot();
    const now = Date.now();
    if (next.stage !== 'closed') {
      projectRoom(next, { kind: 'board' }, now);
      if (next.revision !== this.room.revision) this.commit(next);
    }
    for (const ws of this.sockets()) {
      const session = ws.deserializeAttachment();
      if (!session.authenticated) continue;
      try {
        const viewer = next.stage === 'closed' ? { kind: 'board' } : this.viewer(session.token);
        if (force === ws || session.revision !== next.revision) {
          const state = next.stage === 'closed'
            ? { code: next.code, stage: 'closed', revision: next.revision }
            : projectRoom(next, viewer, now);
          this.send(ws, { type: 'state', state });
          ws.serializeAttachment({ ...session, revision: next.revision });
        }
        if (next.stage === 'closed') ws.close(1000, 'room closed');
      } catch (error) {
        if (error instanceof GameError) {
          this.send(ws, { type: 'error', status: error.status, error: error.message });
          ws.close(4001, 'credentials expired');
        } else {
          console.error('WebSocket delivery failed', error.name);
          ws.close(1011, 'retry');
        }
      }
    }
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== 'GET' || request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
      return response({ error: 'websocket required' }, 426);
    }
    if (request.headers.get('Origin') !== url.origin) return response({ error: 'origin not allowed' }, 403);
    if (!this.room || expiry(this.room) <= Date.now() || this.room.stage === 'closed') {
      return response({ error: 'room closed or expired' }, 410);
    }
    if (this.sockets().length >= MAX_SOCKETS_PER_ROOM) return response({ error: 'too many connections' }, 429);
    const [client, server] = Object.values(new WebSocketPair());
    // Hibernation API: the object can be evicted from memory while this socket stays open.
    // Per-socket state therefore lives in the attachment, not in a field of this class.
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({ authenticated: false, authDeadline: Date.now() + AUTH_DEADLINE_MS });
    await this.schedule();
    return new Response(null, { status: 101, webSocket: client });
  }
}
