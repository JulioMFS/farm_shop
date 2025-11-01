document.addEventListener("DOMContentLoaded", () => {
  const imageZone = document.getElementById("image_zone");
  const imageGallery = document.getElementById("image_gallery");
  const fileInput = document.getElementById("new_images");
  const imageOrderInput = document.getElementById("image_order");

  if (!imageZone || !imageGallery || !fileInput) return;

  let currentImages = []; // {id: <int|null>, src: <string>, file: <File|null>}

  // --- Load existing gallery from Flask template ---
  const existingImages = JSON.parse(imageGallery.dataset.images || "[]");
  currentImages = existingImages.map(img => ({
    id: img.id,
    src: img.filename,
    file: null,
  }));

  renderGallery();

  // --- Prevent browser defaults for drag/drop ---
  ["dragenter", "dragover", "dragleave", "drop"].forEach(evt =>
    imageZone.addEventListener(evt, e => {
      e.preventDefault();
      e.stopPropagation();
    })
  );

  ["dragenter", "dragover"].forEach(evt =>
    imageZone.addEventListener(evt, () =>
      imageZone.classList.add("border-green-500")
    )
  );
  ["dragleave", "drop"].forEach(evt =>
    imageZone.addEventListener(evt, () =>
      imageZone.classList.remove("border-green-500")
    )
  );

  // --- Handle drop ---
  imageZone.addEventListener("drop", e => {
    const files = Array.from(e.dataTransfer.files);
    addNewFiles(files);
  });

  // --- Handle click to open file picker ---
  imageZone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", e => addNewFiles(Array.from(e.target.files)));

  function addNewFiles(files) {
    files.forEach(file => {
      if (!file.type.startsWith("image/")) return;
      const reader = new FileReader();
      reader.onload = e => {
        currentImages.push({ id: null, src: e.target.result, file });
        renderGallery();
      };
      reader.readAsDataURL(file);
    });
  }

  // --- Render all images ---
  function renderGallery() {
    imageGallery.innerHTML = "";
    currentImages.forEach((img, index) => {
      const div = document.createElement("div");
      div.className = "relative group";
      div.dataset.index = index;

      const imageEl = document.createElement("img");
      imageEl.src = img.src;
      imageEl.className =
        "w-32 h-32 object-cover rounded-lg border border-gray-300 cursor-move";

      const removeBtn = document.createElement("button");
      removeBtn.innerHTML = "✖";
      removeBtn.className =
        "absolute top-1 right-1 bg-red-500 text-white rounded-full w-6 h-6 opacity-0 group-hover:opacity-100";
      removeBtn.addEventListener("click", () => {
        currentImages.splice(index, 1);
        renderGallery();
      });

      div.appendChild(imageEl);
      div.appendChild(removeBtn);
      imageGallery.appendChild(div);
    });

    updateOrderInput();
  }

  function updateOrderInput() {
    imageOrderInput.value = JSON.stringify(
      currentImages.map(img => ({ id: img.id, filename: img.src }))
    );
  }

  // --- Enable reordering ---
  if (typeof Sortable !== "undefined") {
    new Sortable(imageGallery, {
      animation: 150,
      onEnd: evt => {
        const newOrder = Array.from(imageGallery.children).map(
          el => parseInt(el.dataset.index)
        );
        currentImages = newOrder.map(i => currentImages[i]);
        renderGallery();
      },
    });
  }
});
