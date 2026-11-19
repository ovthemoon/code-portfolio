// One room state on the server, one projection per connection.
// Hidden fields are left out of the message itself, so there is nothing to find in
// the browser's developer tools. The client never decides what to hide.

export const STAGES = [
  'lobby', 'word', 'write', 'draw', 'describe',
  'guess-0', 'guess-1', 'guess-2', 'result', 'closed',
];

const PRESENCE_WINDOW_MS = 15_000;

// Stages in which the host knows the secret word.
const HOST_WORD_STAGES = ['word', 'write', 'draw', 'describe', 'guess-0', 'guess-1', 'guess-2'];
// Stages in which the public screen and the host watch the work as it is being made.
const LIVE_STAGES = ['write', 'draw', 'describe'];

const isPlayer = (viewer, number) => viewer.kind === 'player' && viewer.number === number;

// What a viewer may receive about the secret, per stage.
// Role holders see only what their step needs. The guesser starts with nothing and gets
// hints in order as the host rejects wrong answers: drawing first, then the description.
function clueFields(room, viewer) {
  const { roles, stage } = room;
  const fields = {};

  if (['board', 'host'].includes(viewer.kind) && LIVE_STAGES.includes(stage)) {
    fields.liveRelay = { description: room.description, drawing: stage === 'write' ? '' : room.drawing };
  }
  if (viewer.kind === 'host' && HOST_WORD_STAGES.includes(stage)) fields.hostWord = room.word;

  if (['word', 'write'].includes(stage) && isPlayer(viewer, roles.author)) fields.word = room.word;
  if (stage === 'write' && isPlayer(viewer, roles.author)) fields.description = room.description;
  if (stage === 'draw' && isPlayer(viewer, roles.illustrator)) {
    fields.description = room.description;
    fields.drawing = room.drawing;
  }
  if (stage === 'describe' && isPlayer(viewer, roles.narrator)) fields.drawing = room.drawing;

  if (stage === 'guess-1') fields.drawing = room.drawing;
  if (stage === 'guess-2') fields.description = room.description;
  if (stage === 'result') fields.word = room.word;
  return fields;
}

function baseView(room, viewer, now) {
  return {
    code: room.code, stage: room.stage, revision: room.revision, roundId: room.roundId,
    paused: room.paused, now, kind: viewer.kind, myNumber: viewer.number ?? null,
    roles: { ...room.roles },
    players: room.players
      .map(player => ({ number: player.number, online: now - player.seenAt < PRESENCE_WINDOW_MS }))
      .sort((a, b) => a.number - b.number),
  };
}

/**
 * Build the view `viewer` is allowed to see. `viewer` is { kind: 'board' },
 * { kind: 'host' } or { kind: 'player', number }. Pure: the room is not modified,
 * and tokens, the word list and other internals are never copied into the view.
 */
export function projectView(room, viewer, now) {
  if (room.stage === 'closed') {
    return { code: room.code, stage: 'closed', kind: viewer.kind, revision: room.revision, now };
  }
  const view = baseView(room, viewer, now);
  if (room.paused) return view;
  return { ...view, ...clueFields(room, viewer) };
}
