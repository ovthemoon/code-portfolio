// Server-side handling of one room action. Same request id never applies twice,
// and a request made for an earlier stage or round is rejected.

export const HANDLED_LIMIT = 1000;
export const MAX_POINTS = 5;
const REQUEST_ID_PATTERN = /^[a-zA-Z0-9_-]{8,80}$/;
const MAX_TEXT_LENGTH = 80;

export class ActionError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

const requireThat = (condition, message, status = 400) => {
  if (!condition) throw new ActionError(message, status);
};

export function createRoom(now) {
  return {
    stage: 'collecting', roundId: 0, revision: 1, touchedAt: now,
    submission: '', score: 0, history: [],
    handled: new Map(),
  };
}

const validateText = value => {
  requireThat(typeof value === 'string' && value.trim().length > 0 && value.length <= MAX_TEXT_LENGTH,
    'text must be 1 to 80 characters');
  return value.trim();
};

const validatePoints = value => {
  requireThat(Number.isInteger(value) && value >= 0 && value <= MAX_POINTS, 'points out of range');
  return value;
};

// Each action: who may use it, in which stages, and the fields it changes.
const ACTIONS = {
  submit: {
    who: 'player', stages: ['collecting'],
    patch: (room, request) => ({ submission: validateText(request.text) }),
  },
  award: {
    who: 'host', stages: ['collecting'],
    patch: (room, request) => {
      const points = validatePoints(request.points);
      return {
        stage: 'result', score: room.score + points,
        history: [...room.history, { roundId: room.roundId, points }],
      };
    },
  },
  next: {
    who: 'host', stages: ['result'],
    patch: room => ({ stage: 'collecting', roundId: room.roundId + 1, submission: '' }),
  },
  close: { who: 'host', stages: ['collecting', 'result'], patch: () => ({ stage: 'closed' }) },
};

const requestKey = (viewer, id) => `${viewer.kind}:${viewer.number ?? 'host'}:${id}`;

function recordHandled(handled, key, limit = HANDLED_LIMIT) {
  const next = new Map(handled).set(key, true);
  if (next.size > limit) next.delete(next.keys().next().value);
  return next;
}

/**
 * Apply `request` for `viewer`. Returns { room, replayed }.
 * Throws ActionError on rejection; a rejected request is not recorded.
 */
export function act(room, viewer, request, now) {
  requireThat(viewer.kind !== 'board', 'public viewers cannot act', 403);
  requireThat(request && typeof request === 'object', 'invalid request');
  const { action, id } = request;
  requireThat(typeof id === 'string' && REQUEST_ID_PATTERN.test(id), 'invalid request id');

  const key = requestKey(viewer, id);
  // Checked before the stage: a retry of something already done is success, not "stale".
  if (room.handled.has(key)) return { room, replayed: true };

  requireThat(room.stage !== 'closed', 'room is closed', 410);
  requireThat(request.stage === room.stage && request.roundId === room.roundId,
    'stage changed, refresh the view', 409);

  const definition = Object.hasOwn(ACTIONS, action) ? ACTIONS[action] : null;
  requireThat(definition, 'unknown action');
  requireThat(viewer.kind === definition.who, `only the ${definition.who} can do this`, 403);
  requireThat(definition.stages.includes(room.stage), 'not available in this stage', 409);

  const next = {
    ...room, ...definition.patch(room, request),
    revision: room.revision + 1, touchedAt: now,
    handled: recordHandled(room.handled, key),
  };
  return { room: next, replayed: false };
}
