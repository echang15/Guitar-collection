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
