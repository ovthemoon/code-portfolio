// Excerpt. Not runnable: Cloudflare Durable Object code, plus the part of the
// create-room route that retries code collisions.
// The decisions are extracted as pure functions in ../lifecycle.mjs and ../room-code.mjs.
// Left out: teacher authentication, rate limiting, the on/off switch for new rooms.
// Names used below but defined elsewhere: expiry (roomExpiry), createRoom, response, GameError.

// Inside the room's Durable Object. One object per room code.
class RelayRoom {
  // Called with a candidate room. False means a live room already owns this code.
  async initialize(candidate) {
    if (this.room && expiry(this.room) > Date.now()) return false;
    this.closeSockets(4004, 'room expired');
    this.presence.clear();
    this.commit({ ...candidate, emptySince: Date.now() });
    await this.schedule();
    return true;
  }

  // Fires at the single scheduled alarm. Expired or closed rooms are wiped completely,
  // so a finished lesson leaves nothing behind that keeps costing money.
  async alarm() {
    if (!this.room) return;
    const now = Date.now();
    for (const ws of this.sockets()) {
      const session = ws.deserializeAttachment();
      if (!session.authenticated && session.authDeadline <= now) ws.close(4001, 'authentication timed out');
    }
    if (expiry(this.room) <= now || this.room.stage === 'closed') {
      this.closeSockets(4004, 'room expired');
      await this.ctx.storage.deleteAll();
      this.room = null;
      this.presence.clear();
      return;
    }
    this.broadcast();
    await this.schedule();
  }
}

// Inside the create-room route: try a few random codes before giving up.
async function allocateRoom(env, body) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const candidate = createRoom(body.minutes, Date.now(), body.words, body.gameMode);
    const stub = env.ROOMS.getByName(candidate.code);
    if (await stub.initialize(candidate)) return response({ code: candidate.code, token: candidate.hostToken }, 201);
  }
  throw new GameError('could not create a room, try again', 503);
}
