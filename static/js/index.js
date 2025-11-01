document.addEventListener("DOMContentLoaded", () => {
    const progressFill = document.getElementById("progress-fill");
    const loadingText = document.getElementById("loading-text");
    const loaderContainer = document.getElementById("loader-container");
    const contentSection = document.getElementById("content-section");
    const productList = document.getElementById("product-list");

    async function loadData() {
        const response = await fetch("/load_data");
        if (!response.ok) throw new Error("Network error");

        const reader = response.body.getReader();
        const contentLength = +response.headers.get("Content-Length");
        let receivedLength = 0;
        let chunks = [];

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
            receivedLength += value.length;

            if (contentLength) {
                const percent = Math.round((receivedLength / contentLength) * 100);
                progressFill.style.width = percent + "%";
                loadingText.textContent = `{{ _('Loading products...') }} ${percent}%`;
            }
        }

        const chunksAll = new Uint8Array(receivedLength);
        let position = 0;
        for (let chunk of chunks) {
            chunksAll.set(chunk, position);
            position += chunk.length;
        }

        const result = new TextDecoder("utf-8").decode(chunksAll);
        const products = JSON.parse(result);

        // Populate the list
        productList.innerHTML = "";
        products.forEach(p => {
            const li = document.createElement("li");
            li.textContent = p.name;
            productList.appendChild(li);
        });

        // Transition to content
        progressFill.style.width = "100%";
        loadingText.textContent = "✓ {{ _('Loaded!') }}";
        setTimeout(() => {
            loaderContainer.classList.add("hidden");
            contentSection.classList.remove("hidden");
        }, 600);
    }

    loadData().catch(err => {
        loadingText.textContent = `{{ _('Error loading data:') }} ${err.message}`;
    });
});
