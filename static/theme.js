// ==================== EXECSLATE THEME TOGGLE ====================
// Shared theme toggle logic — included on every page

(function () {
    const toggleBtn = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    const html = document.documentElement;

    // Apply saved theme on load
    if (localStorage.getItem('theme') === 'dark') {
        html.setAttribute('data-theme', 'dark');
        if (themeIcon) themeIcon.textContent = '☀️';
    }

    // Toggle on click
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const currentTheme = html.getAttribute('data-theme');
            if (currentTheme === 'dark') {
                html.removeAttribute('data-theme');
                localStorage.setItem('theme', 'light');
                if (themeIcon) themeIcon.textContent = '🌙';
            } else {
                html.setAttribute('data-theme', 'dark');
                localStorage.setItem('theme', 'dark');
                if (themeIcon) themeIcon.textContent = '☀️';
            }
        });
    }
})();

// ==================== HAMBURGER MENU ====================
// Auto-initializes on any page with #navHamburger

(function () {
    const hamburger = document.getElementById('navHamburger');
    // Try nav-links first (landing), then nav-right (inner pages)
    const navTarget = document.getElementById('navLinks') || document.getElementById('navRight');

    if (hamburger && navTarget) {
        hamburger.addEventListener('click', () => {
            navTarget.classList.toggle('nav-open');
            hamburger.classList.toggle('is-active');
        });

        // Close menu when any link inside is clicked
        navTarget.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navTarget.classList.remove('nav-open');
                hamburger.classList.remove('is-active');
            });
        });
    }
})();
