import test from 'node:test';
import assert from 'node:assert/strict';
import { startPointerDrag } from './pointerDrag.js';

function fixture() {
  const document = new EventTarget(); document.defaultView = new EventTarget();
  let capture = false;
  const handle = { ownerDocument: document, setPointerCapture() { capture = true; }, hasPointerCapture() { return capture; }, releasePointerCapture() { capture = false; } };
  const events = [];
  const start = { button: 0, isPrimary: true, currentTarget: handle, pointerId: 7, clientX: 10, clientY: 10 };
  const cancel = startPointerDrag(start, {
    getTarget: e => e.clientY < 100 ? { id: 'target', y: e.clientY } : null,
    onStart: () => events.push('start'), onTarget: x => events.push(['hover', x]),
    onDrop: x => events.push(['drop', x]), onCancel: () => events.push('cancel'), onFinish: () => events.push('finish'),
  });
  function dispatch(type, overrides = {}) {
    const event = new Event(type, { cancelable: true });
    Object.assign(event, { pointerId: 7, clientX: 10, clientY: 10, ...overrides });
    document.dispatchEvent(event);
  }
  return { document, events, cancel, dispatch, captured: () => capture };
}

test('pointer drag has a movement threshold and commits once on release, never on hover', () => {
  const f = fixture();
  f.dispatch('pointermove', { clientY: 13 });
  assert.deepEqual(f.events, []);
  for (let y = 20; y < 70; y++) f.dispatch('pointermove', { clientY: y });
  assert.equal(f.events.filter(x => x === 'start').length, 1);
  assert.equal(f.events.filter(x => x[0] === 'drop').length, 0);
  f.dispatch('pointerup', { clientY: 70 });
  f.dispatch('pointerup', { clientY: 71 });
  assert.deepEqual(f.events.filter(x => x[0] === 'drop'), [['drop', { id: 'target', y: 70 }]]);
  assert.equal(f.events.filter(x => x === 'finish').length, 1);
  assert.equal(f.captured(), false);
});

test('outside release, Escape and pointer cancellation never commit', () => {
  for (const method of ['outside', 'escape', 'cancel']) {
    const f = fixture(); f.dispatch('pointermove', { clientY: 40 });
    if (method === 'outside') f.dispatch('pointerup', { clientY: 110 });
    if (method === 'cancel') f.dispatch('pointercancel');
    if (method === 'escape') { const e = new Event('keydown', { cancelable: true }); e.key = 'Escape'; f.document.defaultView.dispatchEvent(e); }
    f.dispatch('pointerup', { clientY: 45 });
    assert.equal(f.events.filter(x => x[0] === 'drop').length, 0);
    assert.equal(f.events.filter(x => x === 'cancel').length, 1);
    assert.equal(f.captured(), false);
  }
});

test('a second pointer cannot commit or start the active gesture; explicit cleanup removes listeners', () => {
  const f = fixture();
  f.dispatch('pointermove', { pointerId: 9, clientY: 50 });
  f.dispatch('pointerup', { pointerId: 9, clientY: 50 });
  assert.deepEqual(f.events, []);
  f.cancel();
  f.dispatch('pointermove', { clientY: 50 });
  f.dispatch('pointerup', { clientY: 50 });
  assert.deepEqual(f.events, ['finish']);
});
