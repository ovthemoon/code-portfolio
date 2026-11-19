// An anonymous wall of short notes. The same submission never lands twice, and
// abuse is slowed down per author and per address. In-memory version: each operation
// builds the next state and commits it only if nothing threw, so a rejected request
// leaves no half-written counters behind.

export const MAX_NOTES = 200;
export const MAX_TEXT_LENGTH = 50;
export const MAX_NAME_LENGTH = 12;

// Example values. The production values differ.
export const MAX_NOTES_PER_AUTHOR = 5;
export const MIN_GAP_PER_AUTHOR_MS = 10_000;
export const MAX_NOTES_PER_IP = 50;
export const MAX_REPORTS_PER_IP = 20;
export const MIN_REPORT_GAP_MS = 500;
export const LIMIT_WINDOW_MS = 600_000;
export const RECEIPT_TTL_MS = 3_600_000;

const REQUEST_ID_PATTERN = /^[a-zA-Z0-9_-]{16,80}$/;
const MAX_ID_LENGTH = 80;
// Control characters and bidirectional overrides become spaces.
const UNSAFE_CHARS = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g;

export class StoreError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

function cleanText(value, max, required = false) {
  if (typeof value !== 'string') throw new StoreError('invalid input');
  const text = value.normalize('NFC').replace(UNSAFE_CHARS, ' ').replace(/\s+/g, ' ').trim();
  if ((required && !text) || [...text].length > max) throw new StoreError('text is empty or too long');
  return text;
}

export function cleanNote(input) {
  if (!input || typeof input !== 'object' || !REQUEST_ID_PATTERN.test(input.requestId ?? '')) {
    throw new StoreError('reopen the form');
  }
  return {
    requestId: input.requestId,
    text: cleanText(input.text, MAX_TEXT_LENGTH, true),
    name: cleanText(input.name, MAX_NAME_LENGTH),
  };
}

export const createState = () => ({
  revision: 0,
  notes: [],              // oldest first
  receipts: new Map(),    // requestId -> { author, expires }
  limits: new Map(),      // key -> { count, last, expires }
  reports: new Map(),     // noteId -> Set of authors
});

const withEntry = (map, key, value) => new Map(map).set(key, value);
const withoutEntry = (map, key) => new Map([...map].filter(([k]) => k !== key));
const dropExpired = (map, now) => new Map([...map].filter(([, entry]) => entry.expires > now));

// The window end is fixed by the first use in the window.
function consume(limits, key, now, max, minGap) {
  const row = limits.get(key);
  if (row && (row.count >= max || now - row.last < minGap)) throw new StoreError('slow down', 429);
  const next = row
    ? { ...row, count: row.count + 1, last: now }
    : { count: 1, last: now, expires: now + LIMIT_WINDOW_MS };
  return withEntry(limits, key, next);
}

// A full wall gives the oldest note's slot to the new one. Otherwise the lowest free slot.
function allocateSlot(notes) {
  if (notes.length >= MAX_NOTES) return { slot: notes[0].slot, evicted: notes[0], kept: notes.slice(1) };
  const used = new Set(notes.map(n => n.slot));
  const slot = Array.from({ length: MAX_NOTES }, (_, i) => i).find(i => !used.has(i));
  return { slot, evicted: null, kept: notes };
}

export function addNote(state, input, author, ip, now) {
  const note = cleanNote(input);
  const receipts = dropExpired(state.receipts, now);
  const limits = dropExpired(state.limits, now);

  // Receipt first: a resend neither adds a note nor uses up any allowance.
  const receipt = receipts.get(note.requestId);
  if (receipt) {
    if (receipt.author !== author) throw new StoreError('reopen the form', 409);
    return { state: { ...state, receipts, limits }, result: { id: note.requestId, repeated: true } };
  }
  if (state.notes.some(n => n.id === note.requestId)) throw new StoreError('reopen the form', 409);

  const limitedByAuthor = consume(limits, `author:${author}`, now, MAX_NOTES_PER_AUTHOR, MIN_GAP_PER_AUTHOR_MS);
  const limitedByIp = consume(limitedByAuthor, `ip:${ip}`, now, MAX_NOTES_PER_IP, 0);
  const { slot, evicted, kept } = allocateSlot(state.notes);
  const created = Object.freeze({ id: note.requestId, slot, text: note.text, name: note.name, createdAt: now });

  return {
    state: {
      revision: state.revision + 1,
      notes: [...kept, created],
      receipts: withEntry(receipts, created.id, { author, expires: now + RECEIPT_TTL_MS }),
      limits: limitedByIp,
      reports: evicted ? withoutEntry(state.reports, evicted.id) : state.reports,
    },
    result: { id: created.id, repeated: false },
  };
}

export function reportNote(state, id, author, ip, now) {
  const limits = consume(dropExpired(state.limits, now), `report:${ip}`, now, MAX_REPORTS_PER_IP, MIN_REPORT_GAP_MS);
  if (typeof id !== 'string' || !state.notes.some(n => n.id === id)) throw new StoreError('note is gone', 404);
  const reporters = new Set(state.reports.get(id) ?? []).add(author);
  return { state: { ...state, limits, reports: withEntry(state.reports, id, reporters) }, result: { ok: true } };
}

export function removeNote(state, id) {
  if (typeof id !== 'string' || id.length > MAX_ID_LENGTH) throw new StoreError('choose a note to remove');
  if (!state.notes.some(n => n.id === id)) return { state, result: { ok: true, removed: false } };
  return {
    state: {
      ...state,
      revision: state.revision + 1,
      notes: state.notes.filter(n => n.id !== id),
      reports: withoutEntry(state.reports, id),
    },
    result: { ok: true, removed: true },
  };
}

export class NoteStore {
  #state = createState();

  #commit(transition) {
    const { state, result } = transition(this.#state);   // throws before anything is stored
    this.#state = state;
    return result;
  }

  add(input, author, ip, now = Date.now()) {
    return this.#commit(state => addNote(state, input, author, ip, now));
  }

  report(id, author, ip, now = Date.now()) {
    return this.#commit(state => reportNote(state, id, author, ip, now));
  }

  remove(id) {
    return this.#commit(state => removeNote(state, id));
  }

  /** What every visitor sees: notes oldest first, plus the revision. */
  snapshot() {
    return { type: 'wall', revision: this.#state.revision, notes: [...this.#state.notes] };
  }

  /** Moderation view: newest first, with how many distinct authors reported each note. */
  admin() {
    const notes = [...this.#state.notes].reverse()
      .map(n => ({ ...n, reports: this.#state.reports.get(n.id)?.size ?? 0 }));
    return { notes };
  }
}
