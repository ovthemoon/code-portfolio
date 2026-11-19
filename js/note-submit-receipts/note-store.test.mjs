import test from 'node:test';
import assert from 'node:assert/strict';
import {
  LIMIT_WINDOW_MS, MAX_NOTES, MAX_NOTES_PER_AUTHOR, MAX_NOTES_PER_IP, MAX_REPORTS_PER_IP,
  MIN_GAP_PER_AUTHOR_MS, MIN_REPORT_GAP_MS, RECEIPT_TTL_MS,
  NoteStore, StoreError, cleanNote,
} from './note-store.mjs';

const NOW = Date.parse('2026-01-15T12:00:00Z');
const GAP = MIN_GAP_PER_AUTHOR_MS + 1;
const requestId = i => `request-note-${String(i).padStart(8, '0')}`;
const note = (i, extra = {}) => ({ requestId: requestId(i), text: `memo ${i}`, name: 'Sam', ...extra });
const status = code => error => error instanceof StoreError && error.status === code;

function setup() {
  const store = new NoteStore();
  const add = (input, author = 'a', ip = 'ip', at = NOW) => store.add(input, author, ip, at);
  return { store, add };
}

function fillWall(add, count) {
  for (let i = 0; i < count; i++) add(note(i), `author${i}`, `ip${i}`);
}

test('the 201st note evicts only the oldest, takes its slot, and the evicted retry stays a no-op', () => {
  const { store, add } = setup();
  fillWall(add, MAX_NOTES);
  // Make the oldest note sit in slot 1, so "its slot" cannot be mistaken for slot 0.
  store.remove(requestId(0));
  add(note(MAX_NOTES), 'refill', 'refill-ip');
  const before = store.snapshot();
  assert.equal(before.notes.length, MAX_NOTES);
  assert.equal(before.notes[0].slot, 1);

  add(note(MAX_NOTES + 1), 'last', 'last');
  const after = store.snapshot();

  assert.equal(after.notes.length, MAX_NOTES);
  assert.equal(after.notes[0].id, requestId(2));
  assert.equal(after.notes.at(-1).slot, 1);
  assert.deepEqual(after.notes.slice(0, -1), before.notes.slice(1));
  assert.equal(after.revision, before.revision + 1);

  // A retry of the submission that was just evicted must not evict another note.
  assert.equal(add(note(1), 'author1', 'ip1').repeated, true);
  assert.deepEqual(store.snapshot(), after);
});

test('while under the limit, a new note takes the lowest free slot', () => {
  const { store, add } = setup();
  fillWall(add, 3);
  store.remove(requestId(1));

  add(note(10), 'other', 'other-ip');

  assert.deepEqual(store.snapshot().notes.map(n => n.slot), [0, 2, 1]);
});

test('resending the same request id is a no-op: nothing added, no revision, no limit used', () => {
  const { store, add } = setup();
  assert.deepEqual(add(note(0)), { id: requestId(0), repeated: false });

  for (let i = 0; i < MAX_NOTES_PER_AUTHOR * 4; i++) {
    assert.deepEqual(add(note(0), 'a', 'ip', NOW + i), { id: requestId(0), repeated: true });
  }

  assert.equal(store.snapshot().notes.length, 1);
  assert.equal(store.snapshot().revision, 1);
  assert.equal(add(note(1), 'a', 'ip', NOW + GAP).repeated, false, 'repeats did not eat the allowance');
});

test('a request id already used by another author is refused', () => {
  const { add } = setup();
  add(note(0));

  assert.throws(() => add(note(0), 'someone-else', 'other-ip'), status(409));
});

test('an id that is still on the wall cannot be reused after its receipt expired', () => {
  const { add } = setup();
  add(note(0));

  assert.throws(() => add(note(0), 'a', 'ip', NOW + RECEIPT_TTL_MS + 1), status(409));
});

test('after the receipt expires, an id that is no longer on the wall is accepted again', () => {
  const { store, add } = setup();
  fillWall(add, MAX_NOTES + 1);
  assert.equal(store.snapshot().notes.some(n => n.id === requestId(0)), false);

  const result = add(note(0), 'author0', 'ip0', NOW + RECEIPT_TTL_MS);

  assert.equal(result.repeated, false);
});

test('an author posting again too soon is throttled, and the store is left unchanged', () => {
  const { store, add } = setup();
  add(note(0));
  const before = store.snapshot();

  assert.throws(() => add(note(1), 'a', 'ip', NOW + 1), status(429));

  assert.deepEqual(store.snapshot(), before);
  assert.equal(add(note(1), 'a', 'ip', NOW + GAP).repeated, false);
});

test('an author is limited per window, and the window is fixed from the first note', () => {
  const { add } = setup();
  for (let i = 0; i < MAX_NOTES_PER_AUTHOR; i++) add(note(i), 'a', 'ip', NOW + i * GAP);

  assert.throws(() => add(note(90), 'a', 'ip', NOW + 6 * GAP), status(429));
  assert.doesNotThrow(() => add(note(91), 'a', 'ip', NOW + LIMIT_WINDOW_MS));
});

test('an address is limited across different authors', () => {
  const { add } = setup();
  for (let i = 0; i < MAX_NOTES_PER_IP; i++) add(note(i), `author${i}`, 'shared-ip');

  assert.throws(() => add(note(90), 'newcomer', 'shared-ip'), status(429));
  assert.doesNotThrow(() => add(note(91), 'newcomer', 'other-ip'));
});

test('a rejected note does not consume the author allowance', () => {
  const { add } = setup();
  for (let i = 0; i < MAX_NOTES_PER_IP; i++) add(note(i), `author${i}`, 'shared-ip');

  assert.throws(() => add(note(90), 'victim', 'shared-ip'), status(429));

  // If the failed attempt had counted, the gap rule would reject this one.
  assert.doesNotThrow(() => add(note(91), 'victim', 'other-ip'));
});

test('text is cleaned and measured in characters, not bytes', () => {
  assert.equal(cleanNote(note(0, { text: '🙂'.repeat(50) })).text, '🙂'.repeat(50));
  assert.equal(cleanNote(note(0, { text: '  a \n\t b\u0000c  ' })).text, 'a b c');
  assert.equal(cleanNote(note(0, { text: 'ab\u202ecd' })).text, 'ab cd');
  assert.equal(cleanNote(note(0, { text: 'e\u0301' })).text, 'é');
});

test('invalid notes are rejected', () => {
  const invalid = [
    note(0, { text: ' ' }), note(0, { text: 'x'.repeat(51) }), note(0, { name: 'x'.repeat(13) }),
    note(0, { text: 42 }), note(0, { name: undefined }),
    { ...note(0), requestId: 'short' }, { ...note(0), requestId: 'has space in it 123' },
    { ...note(0), requestId: undefined }, null,
  ];

  for (const input of invalid) assert.throws(() => cleanNote(input), status(400), JSON.stringify(input));
  assert.equal(cleanNote(note(0, { name: '' })).name, '');
});

test('a report counts once per author, and unknown or removed notes are 404', () => {
  const { store, add } = setup();
  add(note(0));

  store.report(requestId(0), 'v1', 'ip1', NOW);
  store.report(requestId(0), 'v1', 'ip1', NOW + 5000);
  store.report(requestId(0), 'v2', 'ip2', NOW);
  assert.equal(store.admin().notes[0].reports, 2);

  assert.throws(() => store.report('missing-note-id-0000', 'v1', 'ip1', NOW + 10_000), status(404));
  store.remove(requestId(0));
  assert.throws(() => store.report(requestId(0), 'v3', 'ip3', NOW), status(404));
});

test('reports from one address are throttled', () => {
  const { store, add } = setup();
  add(note(0));
  store.report(requestId(0), 'v0', 'same-ip', NOW);

  assert.throws(() => store.report(requestId(0), 'v1', 'same-ip', NOW + 1), status(429));
  for (let i = 1; i < MAX_REPORTS_PER_IP; i++) {
    store.report(requestId(0), `w${i}`, 'same-ip', NOW + i * (MIN_REPORT_GAP_MS + 1));
  }
  assert.throws(() => store.report(requestId(0), 'late', 'same-ip', NOW + 60_000), status(429));
});

test('removing a note deletes it and its reports and bumps the revision once', () => {
  const { store, add } = setup();
  add(note(0));
  store.report(requestId(0), 'v1', 'ip1', NOW);
  const revision = store.snapshot().revision;

  assert.deepEqual(store.remove(requestId(0)), { ok: true, removed: true });

  assert.equal(store.snapshot().revision, revision + 1);
  assert.equal(store.admin().notes.length, 0);
});

test('removing an unknown id changes nothing', () => {
  const { store, add } = setup();
  add(note(0));
  const before = store.snapshot();

  assert.deepEqual(store.remove('no-such-note-id-000'), { ok: true, removed: false });

  assert.deepEqual(store.snapshot(), before);
  assert.throws(() => store.remove(42), status(400));
  assert.throws(() => store.remove('x'.repeat(81)), status(400));
});

test('an evicted note takes its reports with it', () => {
  const { store, add } = setup();
  fillWall(add, MAX_NOTES);
  store.report(requestId(0), 'v1', 'ip1', NOW);

  add(note(MAX_NOTES), 'last', 'last');

  assert.equal(store.admin().notes.every(n => n.reports === 0), true);
  assert.throws(() => store.report(requestId(0), 'v2', 'ip2', NOW), status(404));
});

test('the admin list is newest first and carries report counts', () => {
  const { store, add } = setup();
  fillWall(add, 3);
  store.report(requestId(1), 'v1', 'ip1', NOW);

  assert.deepEqual(store.admin().notes.map(n => [n.id, n.reports]), [
    [requestId(2), 0], [requestId(1), 1], [requestId(0), 0],
  ]);
});

test('snapshots are copies: changing one does not change the store', () => {
  const { store, add } = setup();
  add(note(0));

  const snapshot = store.snapshot();
  snapshot.notes.pop();
  snapshot.revision = 99;

  assert.equal(store.snapshot().notes.length, 1);
  assert.equal(store.snapshot().revision, 1);
});
