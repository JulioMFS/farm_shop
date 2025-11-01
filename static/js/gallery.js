document.addEventListener("DOMContentLoaded", async () => {
    const progressFill = document.getElementById("progress-fill");
    const loadingText = document.getElementById("loading-text");
    const loaderContainer = document.getElementById("loader-container");
    const gallerySection = document.getElementById("gallery-section");
    const imageGallery = document.getElementById("image-gallery");

    try {
        const response = await fetch("/load_images");
        if (!response.ok) throw new Error("Failed to load image list");

        const imageUrls = await response.json();
        const total = imageUrls.length;
        let loaded = 0;

        imageUrls.forEach(url => {
            const img = new Image();
            img.src = url;
            img.onload = () => {
                loaded++;
                imageGallery.appendChild(img);

                const percent = Math.round((loaded / total) * 100);
                progressFill.style.width = percent + "%";
                loadingText.textContent = `${percent}% {{ _('Loaded...') }}`;

                if (loaded === total) {
                    loadingText.textContent = "✓ {{ _('All images loaded!') }}";
                    setTimeout(() => {
                        loaderContainer.classList.add("hidden");
                        gallerySection.classList.remove("hidden");
                    }, 500);
                }
            };
            img.onerror = () => {
                loaded++;
                console.error("Failed to load image:", url);
            };
        });
    } catch (err) {
        loadingText.textContent = `{{ _('Error loading images:') }} ${err.message}`;
    }
});
