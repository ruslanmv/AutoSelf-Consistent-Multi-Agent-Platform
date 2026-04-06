// Slide UX helpers:
// 1) Keyboard navigation (ArrowLeft / ArrowRight)
// 2) Auto-hide slide menu/controls + press "H" to toggle always-hidden
(() => {
  const slides = [
    "slide01-title.html",
    "slide02-problem.html",
    "slide03-gap.html",
    "slide04-architecture.html",
    "slide05-evc-loop.html",
    "slide06-hybrid-verification.html",
    "slide07-self-consistency.html",
    "slide08-hazard.html",
    "slide09-fault.html",
    "slide10-benchmark.html",
    "slide11-ablation.html",
    "slide12-implications.html",
    "slide13-conclusions.html"
  ];

  const current = (location.pathname.split('/').pop() || '').split('?')[0].split('#')[0];
  const idx = slides.indexOf(current);
  if (idx === -1) return;

  const root = document.documentElement;

  const isEditableTarget = (el) => {
    if (!el) return false;
    const tag = (el.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (el.isContentEditable) return true;
    return false;
  };

  // ---------- Controls auto-hide ----------
  // We tag likely "menu/controls" nodes with a helper class so CSS can hide them.
  const CONTROL_CLASS = "__autoself_controls";
  const controlSelectors = [
    // If you already have a known wrapper, add it here:
    ".slide-controls",
    ".slide-menu",
    ".controls",
    ".nav",
    ".navbar",
    ".toolbar",
    ".menu",
    ".menubar",

    // Common patterns for buttons/containers:
    "[data-slide-controls]",
    "[data-controls]",
    "[role='toolbar']",
    "[aria-label*='slide' i]",
    "[aria-label*='slides' i]",
    "[aria-label*='menu' i]",
    "[title*='slide' i]",
    "[title*='menu' i]",

    // If your nav buttons are in a fixed corner:
    "button[onclick*='slide' i]",
    "a[href*='slide' i]"
  ];

  const markControls = () => {
    const candidates = new Set();
    controlSelectors.forEach((sel) => {
      document.querySelectorAll(sel).forEach((el) => candidates.add(el));
    });

    // Heuristic: also mark small fixed-position UI elements near edges (often nav/menu)
    document.querySelectorAll("body *").forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.position !== "fixed") return;
      const r = el.getBoundingClientRect();
      const tiny = (r.width <= 80 && r.height <= 80);
      const corner =
        (r.left <= 20 && r.top <= 20) ||
        (r.right >= (window.innerWidth - 20) && r.top <= 20) ||
        (r.left <= 20 && r.bottom >= (window.innerHeight - 20)) ||
        (r.right >= (window.innerWidth - 20) && r.bottom >= (window.innerHeight - 20));
      if (tiny && corner) candidates.add(el);
    });

    candidates.forEach((el) => el.classList.add(CONTROL_CLASS));
  };

  // Reveal controls briefly unless user forced-hide
  let revealTimer = null;
  const revealControls = () => {
    if (root.classList.contains("hide-controls")) return;
    root.classList.add("show-controls");
    clearTimeout(revealTimer);
    revealTimer = setTimeout(() => root.classList.remove("show-controls"), 1200);
  };

  // Toggle always-hidden on "H"
  const toggleHideControls = () => {
    const nowHidden = !root.classList.contains("hide-controls");
    root.classList.toggle("hide-controls", nowHidden);
    if (nowHidden) root.classList.remove("show-controls");
    else revealControls();
  };

  // Mark controls after DOM is ready, then auto-hide behavior
  const initControls = () => {
    markControls();
    // show once, then fade out
    revealControls();

    ["mousemove", "mousedown", "touchstart"].forEach((evt) =>
      window.addEventListener(evt, revealControls, { passive: true })
    );
    window.addEventListener("keydown", (e) => {
      if (e.defaultPrevented) return;
      if (isEditableTarget(document.activeElement)) return;

      // "H" toggles hide/unhide controls
      if (!e.altKey && !e.ctrlKey && !e.metaKey && e.key && e.key.toLowerCase() === "h") {
        e.preventDefault();
        toggleHideControls();
        return;
      }

      // Any other key press briefly reveals (unless force-hidden)
      revealControls();
    }, { passive: false });

    window.addEventListener("resize", () => {
      // re-run marking in case layout/controls change
      markControls();
    }, { passive: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initControls);
  } else {
    initControls();
  }

  // ---------- Arrow navigation ----------
  document.addEventListener('keydown', (e) => {
    if (e.defaultPrevented) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (isEditableTarget(document.activeElement)) return;

    let nextIdx = null;
    if (e.key === 'ArrowRight') nextIdx = Math.min(idx + 1, slides.length - 1);
    if (e.key === 'ArrowLeft') nextIdx = Math.max(idx - 1, 0);

    if (nextIdx === null || nextIdx === idx) return;

    e.preventDefault();
    // Preserve base path (GitHub Pages subpath safe)
    const base = location.pathname.replace(/[^/]*$/, '');
    location.href = base + slides[nextIdx];
  }, { passive: false });
})();
