// Confirm destructive actions.
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  });
});

// Gallery: clicking a thumbnail swaps the main photo.
const mainImg = document.getElementById("main-photo");
if (mainImg) {
  const link = document.getElementById("main-photo-link");
  const caption = document.getElementById("main-caption");
  document.querySelectorAll(".thumb img").forEach((img) => {
    img.addEventListener("click", () => {
      mainImg.src = img.dataset.full;
      link.href = img.dataset.full;
      caption.textContent = img.dataset.caption;
    });
  });
}

// Show archive fields only when status is "archived".
const status = document.getElementById("f-status");
const archiveFields = document.getElementById("archive-fields");
if (status && archiveFields) {
  const sync = () => { archiveFields.hidden = status.value !== "archived"; };
  status.addEventListener("change", sync);
  sync();
}

// File inputs: show chosen file names; support drag and drop.
document.querySelectorAll(".dropzone").forEach((zone) => {
  const input = zone.querySelector("input[type=file]");
  const label = zone.querySelector("span");
  const original = label.textContent;
  const update = () => {
    const n = input.files.length;
    label.textContent = n ? `${n} photo${n > 1 ? "s" : ""} selected` : original;
  };
  input.addEventListener("change", update);
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("over");
    input.files = e.dataTransfer.files;
    update();
  });
});

// --- Showroom screensaver ---------------------------------------------------
// After a period of inactivity, show a full-screen gallery of every photo in the
// collection. Any mouse movement, touch, click or key press dismisses it.
(() => {
  const root = document.getElementById("screensaver");
  if (!root) return;

  const SLIDE_MS = 8000;
  const MOVE_THRESHOLD = 10;   // px of pointer travel needed to dismiss (ignores jitter)
  const ARM_DELAY_MS = 600;    // ignore input right after it opens
  const idleSeconds = parseInt(document.body.dataset.idle || "0", 10);

  const slides = [...root.querySelectorAll(".ss-slide")];
  const info = document.getElementById("ss-info");
  const brandEl = document.getElementById("ss-brand");
  const modelEl = document.getElementById("ss-model");
  const detailsEl = document.getElementById("ss-details");
  const captionEl = document.getElementById("ss-caption");
  const emptyEl = document.getElementById("ss-empty");
  const progress = document.getElementById("ss-progress");
  const clock = document.getElementById("ss-clock");
  root.style.setProperty("--ss-duration", `${SLIDE_MS}ms`);

  let active = false, photos = [], index = 0, slot = 0;
  let slideTimer = null, clockTimer = null, idleTimer = null;
  let armedAt = 0, origin = null, wentFullscreen = false;

  const shuffle = (list) => {
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [list[i], list[j]] = [list[j], list[i]];
    }
    return list;
  };

  const preload = (src) => new Promise((resolve) => {
    const img = new Image();
    img.onload = img.onerror = () => resolve(img);
    img.src = src;
  });

  const tickClock = () => {
    clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  };

  async function show(photo) {
    await preload(photo.src);
    if (!active) return;
    slot = 1 - slot;
    const next = slides[slot], prev = slides[1 - slot];
    next.querySelector("img").src = photo.src;
    next.querySelector(".ss-backdrop").style.backgroundImage = `url("${photo.thumb}")`;
    next.dataset.motion = String(index % 2);
    // Restart the Ken Burns animation on the incoming slide.
    next.classList.remove("is-current");
    void next.offsetWidth;
    next.classList.add("is-current");
    prev.classList.remove("is-current");

    info.classList.remove("is-in");
    setTimeout(() => {
      if (!active) return;
      brandEl.textContent = photo.brand;
      modelEl.textContent = photo.model;
      detailsEl.textContent = photo.details + (photo.status === "archived" ? " · Archived" : "");
      captionEl.textContent = photo.caption;
      info.classList.add("is-in");
    }, 450);

    progress.classList.remove("is-running");
    void progress.offsetWidth;
    progress.classList.add("is-running");
  }

  function advance() {
    if (!active || !photos.length) return;
    show(photos[index]);
    index = (index + 1) % photos.length;
    if (index === 0) shuffle(photos);
    // Warm the cache for the next image while this one is on screen.
    if (photos.length > 1) preload(photos[index].src);
  }

  async function start({ fullscreen = false } = {}) {
    if (active) return;
    active = true;
    clearTimeout(idleTimer);
    armedAt = Date.now() + ARM_DELAY_MS;
    origin = null;
    document.body.classList.add("ss-active");
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => root.classList.add("is-on"));
    tickClock();
    clockTimer = setInterval(tickClock, 15000);

    if (fullscreen && root.requestFullscreen && !document.fullscreenElement) {
      root.requestFullscreen().then(() => { wentFullscreen = true; }).catch(() => {});
    }

    try {
      const res = await fetch("/api/gallery", { credentials: "same-origin" });
      photos = res.ok ? shuffle(await res.json()) : [];
    } catch {
      photos = [];
    }
    if (!active) return;
    index = 0;
    emptyEl.hidden = photos.length > 0;
    info.hidden = photos.length === 0;
    if (photos.length) {
      advance();
      if (photos.length > 1) slideTimer = setInterval(advance, SLIDE_MS);
    }
  }

  function stop() {
    if (!active) return;
    active = false;
    clearInterval(slideTimer);
    clearInterval(clockTimer);
    root.classList.remove("is-on");
    info.classList.remove("is-in");
    progress.classList.remove("is-running");
    document.body.classList.remove("ss-active");
    if (wentFullscreen && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    wentFullscreen = false;
    setTimeout(() => {
      if (active) return;
      root.hidden = true;
      root.setAttribute("aria-hidden", "true");
      slides.forEach((s) => s.classList.remove("is-current"));
    }, 900);
    resetIdle();
  }

  function resetIdle() {
    clearTimeout(idleTimer);
    if (idleSeconds > 0 && !active) idleTimer = setTimeout(() => start(), idleSeconds * 1000);
  }

  // Dismiss on real pointer movement; reset the idle timer otherwise.
  document.addEventListener("mousemove", (e) => {
    if (!active) return resetIdle();
    if (Date.now() < armedAt) return;
    if (!origin) { origin = { x: e.clientX, y: e.clientY }; return; }
    if (Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > MOVE_THRESHOLD) stop();
  }, { passive: true });

  const dismissOrReset = (e) => {
    if (!active) return resetIdle();
    if (Date.now() < armedAt) return;
    if (e.type === "keydown" || e.type === "mousedown") e.preventDefault();
    stop();
  };
  ["mousedown", "keydown", "touchstart", "wheel", "pointerdown"].forEach((type) =>
    document.addEventListener(type, dismissOrReset, { passive: type !== "keydown" && type !== "mousedown" }));
  window.addEventListener("scroll", () => { if (!active) resetIdle(); }, { passive: true });
  // Swallow the click that ends a dismissal so it doesn't hit whatever is underneath.
  root.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); });

  const button = document.getElementById("showcase-start");
  if (button) button.addEventListener("click", (e) => {
    e.stopPropagation();
    start({ fullscreen: true });
  });

  resetIdle();
})();
