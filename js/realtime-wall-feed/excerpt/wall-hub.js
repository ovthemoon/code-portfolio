// Excerpt. Not runnable: Cloudflare Durable Object code that needs the Workers runtime.
// Server side of ../wall-feed.mjs. Wall sockets are receive-only: the server pushes
// snapshots, and any message a client sends closes the connection.
// Left out: the other socket kinds, storage setup, admin routes, the write route.
// Names used below but defined elsewhere: json, this.wall (the note store), this.send.
import { DurableObject } from 'cloudflare:workers';

// Example value. The production value differs.
const MAX_WALL_SOCKETS = 500;

export class WallHub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    // The client's heartbeat is answered by the platform without waking the object.
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('keepalive', 'alive'));
  }

  // Push the current snapshot to every wall socket. Called after each accepted change.
  broadcastWall() {
    const sockets = this.ctx.getWebSockets('wall');
    if (!sockets.length) return;
    const packet = JSON.stringify(this.wall.snapshot());
    for (const socket of sockets) this.send(socket, packet);
  }

  // Any client message on a wall socket is a protocol violation.
  webSocketMessage(socket) {
    if (socket.deserializeAttachment()?.kind === 'wall') {
      socket.close(1008, 'read only');
    }
  }

  async fetch(request) {
    if (request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
      return json({ error: 'websocket required' }, 426);
    }
    if (request.headers.get('Origin') !== this.env.ALLOWED_ORIGIN) {
      return json({ error: 'origin not allowed' }, 403);
    }
    if (this.ctx.getWebSockets('wall').length >= MAX_WALL_SOCKETS) {
      return json({ error: 'too many connections' }, 503);
    }
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server, ['wall']);
    server.serializeAttachment({ kind: 'wall' });
    // The first snapshot goes out right away, so the client can leave its HTTP fallback.
    server.send(JSON.stringify(this.wall.snapshot()));
    return new Response(null, { status: 101, webSocket: client });
  }
}
