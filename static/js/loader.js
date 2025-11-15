// --- Global Loading Overlay Controller (CSP-safe) ---
export function showLoading() {
    const overlay = document.getElementById("loading-overlay");
    if (overlay) overlay.classList.remove("loading-hidden");
}

export function hideLoading() {
    const overlay = document.getElementById("loading-overlay");
    if (overlay) overlay.classList.add("loading-hidden");
    resetProgress();
}

export function previewLoading() {
    showLoading();
    setTimeout(hideLoading, 200);
}

// --- Upload progress functions ---
export function startProgress() {
    const container = document.getElementById("upload-progress-container");
    if (container) container.classList.remove("hidden");
    updateProgress(0);
}

export function updateProgress(percent) {
    const bar = document.getElementById("upload-progress-bar");
    const text = document.getElementById("upload-progress-text");
    if (bar) bar.style.width = percent + "%";
    if (text) text.textContent = percent + "%";
}

export function finishProgress() {
    updateProgress(100);
    setTimeout(() => {
        const container = document.getElementById("upload-progress-container");
        if (container) container.classList.add("hidden");
        hideLoading();
    }, 500);
}

export function resetProgress() {
    updateProgress(0);
}
