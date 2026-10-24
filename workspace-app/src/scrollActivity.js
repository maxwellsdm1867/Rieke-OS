// One passive observer for native scrolling, including nested/retained panes.
// No wheel interception, React renders, or changes to scroll position/geometry.
export function installScrollActivity(root = document) {
  const pending = new Map();
  const onScroll = ({target}) => {
    if (!target?.setAttribute) return;
    clearTimeout(pending.get(target));
    target.setAttribute('data-scroll-active', '');
    pending.set(target, setTimeout(() => {
      target.removeAttribute('data-scroll-active');
      pending.delete(target);
    }, 800));
  };
  root.addEventListener('scroll', onScroll, {capture: true, passive: true});
  return () => {
    root.removeEventListener('scroll', onScroll, true);
    for (const [element, timer] of pending) {
      clearTimeout(timer);
      element.removeAttribute('data-scroll-active');
    }
    pending.clear();
  };
}
