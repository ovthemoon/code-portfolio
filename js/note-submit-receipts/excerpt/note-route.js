// Excerpt. Not runnable: the write route inside a Cloudflare Durable Object.
// Left out: routing, the admin routes, and the cookie handling behind visitorId().
// Names used below but defined elsewhere: json, digest (hash), readJson, this.notes
// (the store in ../note-store.mjs, backed by SQL in production), this.broadcast.

async function handleNotePost(request) {
  // A hash of an anonymous per-browser cookie. Missing cookie: 403, reload the page first.
  const author = await this.visitorId(request);
  const ip = await digest(request.headers.get('CF-Connecting-IP') ?? 'unknown');
  const input = await readJson(request);
  // One transaction: validation, limits, slot allocation and the insert succeed or fail together.
  const result = this.ctx.storage.transactionSync(() => this.notes.add(input, author, ip));
  // A resend changes nothing, so nobody is notified.
  if (!result.repeated) this.broadcast();
  return json({ ...result, ...this.notes.snapshot() });
}
