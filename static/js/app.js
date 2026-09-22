// ProjectPulse AI General Application Scripts & CSRF Interceptor

(function() {
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && options.method && options.method.toUpperCase() !== 'GET' && options.method.toUpperCase() !== 'HEAD') {
            options.headers = options.headers || {};
            if (options.headers instanceof Headers) {
                if (!options.headers.has('X-CSRFToken')) {
                    options.headers.append('X-CSRFToken', meta.getAttribute('content'));
                }
            } else if (Array.isArray(options.headers)) {
                let hasCsrf = options.headers.some(h => h[0].toLowerCase() === 'x-csrftoken');
                if (!hasCsrf) {
                    options.headers.push(['X-CSRFToken', meta.getAttribute('content')]);
                }
            } else {
                if (!options.headers['X-CSRFToken']) {
                    options.headers['X-CSRFToken'] = meta.getAttribute('content');
                }
            }
        }
        return originalFetch(url, options);
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss flash alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            if (typeof bootstrap !== 'undefined' && bootstrap.Alert) {
                try {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance ? bootstrap.Alert.getOrCreateInstance(alert) : new bootstrap.Alert(alert);
                    if (bsAlert) bsAlert.close();
                } catch (e) {}
            }
        }, 5000);
    });

    // Initialize all Bootstrap tooltips if any
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.forEach(function (tooltipTriggerEl) {
            try {
                new bootstrap.Tooltip(tooltipTriggerEl);
            } catch (e) {}
        });
    }

    // Responsive Mobile Sidebar Toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.querySelector('.app-sidebar');
    const backdrop = document.getElementById('sidebarBackdrop');

    if (sidebarToggle && sidebar && backdrop) {
        function openSidebar() {
            sidebar.classList.add('sidebar-open');
            backdrop.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeSidebar() {
            sidebar.classList.remove('sidebar-open');
            backdrop.classList.remove('active');
            document.body.style.overflow = '';
        }

        sidebarToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (sidebar.classList.contains('sidebar-open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        backdrop.addEventListener('click', closeSidebar);

        window.addEventListener('resize', function() {
            if (window.innerWidth >= 992 && sidebar.classList.contains('sidebar-open')) {
                closeSidebar();
            }
        });
    }
});


