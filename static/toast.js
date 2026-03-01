// ==================== EXECSLATE TOAST NOTIFICATIONS ====================
// Lightweight toast system for success/error/info messages

(function () {
    // Create toast container if it doesn't exist
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {string} type - 'success' | 'error' | 'info' | 'warning'
     * @param {number} duration - Duration in ms (default 4000)
     */
    window.showToast = function (message, type = 'info', duration = 4000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };

        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;

        container.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => toast.classList.add('toast-visible'));

        // Auto-dismiss
        setTimeout(() => {
            toast.classList.remove('toast-visible');
            toast.addEventListener('transitionend', () => toast.remove());
        }, duration);
    };

    // Auto-show toasts from URL params (e.g., ?msg=Report+saved&type=success)
    const params = new URLSearchParams(window.location.search);
    const msg = params.get('msg');
    const msgType = params.get('type') || 'info';
    if (msg) {
        // Small delay so page renders first
        setTimeout(() => showToast(decodeURIComponent(msg), msgType), 300);
    }
})();
