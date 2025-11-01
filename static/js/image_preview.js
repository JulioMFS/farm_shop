document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.getElementById("drop_zone");
  const fileInput = document.getElementById("new_images");
  const preview = document.getElementById("preview");

  if (!dropZone || !fileInput || !preview) return;

  let currentFiles = [];

  // --- Prevent browser default behavior ---
  ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, e => {
      e.preventDefault();
      e.stopPropagation();
    });
  });

  ["dragenter", "dragover"].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add("border-green-500"));
  });
  ["dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove("border-green-500"));
  });

  // --- Handle file drops ---
  dropZone.addEventListener("drop", e => {
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  });

  // --- Handle file picker ---
  fileInput.addEventListener("change", e => {
    const files = Array.from(e.target.files);
    addFiles(files);
  });

  // --- Add files to preview and store them ---
  function addFiles(files) {
    files.forEach(file => {
      if (!file.type.startsWith("image/")) return;
      currentFiles.push(file);
    });
    updatePreview();
  }

  // --- Update preview thumbnails ---
  function updatePreview() {
    preview.innerHTML = "";
    currentFiles.forEach((file, index) => {
      const reader = new FileReader();
      reader.onload = e => {
        const img = document.createElement("img");
        img.src = e.target.result;
        img.className = "w-32 h-32 object-cover rounded-lg border border-gray-300 cursor-move";
        img.dataset.index = index;
        preview.appendChild(img);
      };
      reader.readAsDataURL(file);
    });
    fileInput.files = FileListItem(...currentFiles);
  }

  // --- Create a new FileList (browser trick) ---
  function FileListItem(...files) {
    const dataTransfer = new DataTransfer();
    files.forEach(f => dataTransfer.items.add(f));
    return dataTransfer.files;
  }

  // --- Enable drag reordering of previews ---
  if (typeof Sortable !== "undefined") {
    new Sortable(preview, {
      animation: 150,
      onEnd: () => {
        const newOrder = Array.from(preview.children).map(el => parseInt(el.dataset.index));
        currentFiles = newOrder.map(i => currentFiles[i]);
        fileInput.files = FileListItem(...currentFiles);
      }
    });
  }
});
