import test from 'node:test';
import assert from 'node:assert/strict';
import { STAGES, projectView } from './project-view.mjs';

const NOW = 5_000;
// Distinct markers, so a leak shows up as a substring of the serialized view.
const SECRET = { word: 'SECRET-WORD', description: 'DESCRIPTION-TEXT', drawing: 'DRAWING-DATA' };
const TOKENS = { host: 'host-token-aaaa', 1: 'player-token-1111', 2: 'player-token-2222' };

const roles = { author: 1, illustrator: 2, narrator: 3, guesser: 4 };
const viewers = {
  board: { kind: 'board' },
  host: { kind: 'host' },
  author: { kind: 'player', number: 1 },
  illustrator: { kind: 'player', number: 2 },
  narrator: { kind: 'player', number: 3 },
  guesser: { kind: 'player', number: 4 },
};

const roomAt = (stage, overrides = {}) => ({
  code: '123456', stage, revision: 7, roundId: 2, paused: false, roles,
  word: SECRET.word, description: SECRET.description, drawing: SECRET.drawing,
  hostToken: TOKENS.host,
  players: [1, 2, 3, 4].map(number => ({ number, token: `player-token-${number}${number}${number}${number}`, seenAt: NOW })),
  ...overrides,
});

const markers = view => {
  const text = JSON.stringify(view);
  return Object.keys(SECRET).filter(name => text.includes(SECRET[name])).sort();
};

// Which secrets each viewer may receive, per stage. The hint stages reveal in order:
// first the drawing to everyone, then the description to everyone.
const EXPECTED = {
  word: { host: ['word'], author: ['word'] },
  write: { host: ['description', 'word'], board: ['description'], author: ['description', 'word'] },
  draw: {
    host: ['description', 'drawing', 'word'], board: ['description', 'drawing'],
    illustrator: ['description', 'drawing'],
  },
  describe: {
    host: ['description', 'drawing', 'word'], board: ['description', 'drawing'],
    narrator: ['drawing'],
  },
  'guess-0': { host: ['word'] },
  'guess-1': Object.fromEntries(Object.keys(viewers).map(name => [name, name === 'host' ? ['drawing', 'word'] : ['drawing']])),
  'guess-2': Object.fromEntries(Object.keys(viewers).map(name => [name, name === 'host' ? ['description', 'word'] : ['description']])),
  result: Object.fromEntries(Object.keys(viewers).map(name => [name, ['word']])),
};

for (const stage of Object.keys(EXPECTED)) {
  test(`stage ${stage}: each viewer receives exactly the fields they are allowed`, () => {
    for (const [name, viewer] of Object.entries(viewers)) {
      const received = markers(projectView(roomAt(stage), viewer, NOW));

      assert.deepEqual(received, EXPECTED[stage][name] ?? [], `${name} in ${stage}`);
    }
  });
}

test('the guesser is not hidden from the clues forever: they arrive stage by stage', () => {
  const seen = stage => markers(projectView(roomAt(stage), viewers.guesser, NOW));

  assert.deepEqual(['guess-0', 'guess-1', 'guess-2', 'result'].map(seen),
    [[], ['drawing'], ['description'], ['word']]);
});

test('the guesser never sees the live work of earlier roles', () => {
  for (const stage of ['write', 'draw', 'describe']) {
    const view = projectView(roomAt(stage), viewers.guesser, NOW);

    assert.equal(view.liveRelay, undefined, stage);
    assert.deepEqual(markers(view), [], stage);
  }
});

test('the public screen and host get live work, with no drawing while the text is written', () => {
  const write = projectView(roomAt('write', { drawing: '' }), viewers.board, NOW);
  const draw = projectView(roomAt('draw'), viewers.board, NOW);

  assert.deepEqual(write.liveRelay, { description: SECRET.description, drawing: '' });
  assert.deepEqual(draw.liveRelay, { description: SECRET.description, drawing: SECRET.drawing });
});

test('credentials never appear in any view', () => {
  for (const stage of STAGES) {
    for (const viewer of Object.values(viewers)) {
      const text = JSON.stringify(projectView(roomAt(stage), viewer, NOW));

      for (const token of Object.values(TOKENS)) assert.ok(!text.includes(token), `${stage}`);
      assert.ok(!text.includes('player-token'), `${stage}`);
    }
  }
});

test('the player list exposes only number and presence', () => {
  const view = projectView(roomAt('word'), viewers.board, NOW);

  assert.deepEqual(view.players[0], { number: 1, online: true });
});

test('a paused room hides every clue from every viewer', () => {
  for (const stage of ['word', 'write', 'draw', 'describe', 'guess-1', 'result']) {
    for (const viewer of Object.values(viewers)) {
      assert.deepEqual(markers(projectView(roomAt(stage, { paused: true }), viewer, NOW)), [], stage);
    }
  }
});

test('a closed room is reduced to the minimum, for everyone', () => {
  const view = projectView(roomAt('closed'), viewers.host, NOW);

  assert.deepEqual(view, { code: '123456', stage: 'closed', kind: 'host', revision: 7, now: NOW });
});

test('each view says who it was built for', () => {
  assert.equal(projectView(roomAt('word'), viewers.board, NOW).kind, 'board');
  const mine = projectView(roomAt('word'), viewers.narrator, NOW);

  assert.equal(mine.kind, 'player');
  assert.equal(mine.myNumber, 3);
  assert.equal(projectView(roomAt('word'), viewers.board, NOW).myNumber, null);
});

test('projection does not modify the room', () => {
  const room = roomAt('write');
  const frozen = JSON.parse(JSON.stringify(room));
  const deepFreeze = value => {
    if (value && typeof value === 'object') Object.values(value).forEach(deepFreeze);
    return Object.freeze(value);
  };
  deepFreeze(room);

  for (const viewer of Object.values(viewers)) projectView(room, viewer, NOW);

  assert.deepEqual(room, frozen);
});
