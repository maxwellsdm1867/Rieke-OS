// Internal list dragging: hover is visual only; one pointer-up commits a drop.
export function startPointerDrag(event, { getTarget, onStart, onTarget, onDrop, onCancel, onFinish, threshold = 5 }) {
  if (event.button !== 0 || event.isPrimary === false) return null;
  const handle = event.currentTarget;
  const document = handle.ownerDocument;
  const window = document.defaultView;
  const { pointerId, clientX, clientY } = event;
  let started = false, finished = false;
  try { handle.setPointerCapture?.(pointerId); } catch { /* Document listeners retain the gesture. */ }
  function finish(cancelled = false) {
    if (finished) return;
    finished = true;
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
    document.removeEventListener('pointercancel', cancel);
    document.removeEventListener('selectstart', preventSelection);
    window?.removeEventListener('blur', cancel);
    window?.removeEventListener('keydown', key);
    try { if (handle.hasPointerCapture?.(pointerId)) handle.releasePointerCapture(pointerId); } catch { /* Already released. */ }
    if (cancelled && started) onCancel?.();
    onFinish?.();
  }
  function preventSelection(event) { if (started) event.preventDefault(); }
  function move(event) {
    if (event.pointerId !== pointerId || finished) return;
    if (!started) {
      if (Math.hypot(event.clientX - clientX, event.clientY - clientY) < threshold) return;
      started = true;
      onStart?.();
    }
    event.preventDefault();
    onTarget?.(getTarget(event));
  }
  function up(event) {
    if (event.pointerId !== pointerId || finished) return;
    const target = started ? getTarget(event) : null;
    try {
      if (started) event.preventDefault();
      if (target) onDrop?.(target);
      else if (started) onCancel?.();
    } finally { finish(); }
  }
  function cancel() { finish(true); }
  function key(event) { if (event.key === 'Escape') { event.preventDefault(); cancel(); } }
  document.addEventListener('pointermove', move, { passive: false });
  document.addEventListener('pointerup', up, { passive: false });
  document.addEventListener('pointercancel', cancel);
  document.addEventListener('selectstart', preventSelection);
  window?.addEventListener('blur', cancel);
  window?.addEventListener('keydown', key);
  return cancel;
}
