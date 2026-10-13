(() => {
    function updateCountdowns() {
        document.querySelectorAll('[data-opens-at]').forEach((element) => {
            const seconds = Math.max(0, Math.ceil((Date.parse(element.dataset.opensAt) - Date.now()) / 1000));
            if (!Number.isFinite(seconds)) return;
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor(seconds % 86400 / 3600);
            const minutes = Math.floor(seconds % 3600 / 60);
            element.textContent = seconds > 0
                ? `Mai sunt ${days} zile, ${hours} ore, ${minutes} minute și ${seconds % 60} secunde.`
                : 'Momentul a sosit. Redeschide capsula din colecție pentru a continua.';
            if (seconds === 0 && !element.dataset.refreshing) {
                element.dataset.refreshing = 'true';
                fetch(element.dataset.detailUrl).then(async (response) => {
                    if (!response.ok || response.redirected || !element.isConnected) return;
                    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
                    const surface = page.querySelector('.capsule-reader');
                    // The server, rather than the browser clock, authorizes the action.
                    if (surface && !surface.querySelector('[data-opens-at]')) {
                        element.closest('.capsule-reader').replaceWith(surface);
                        document.dispatchEvent(new Event('capsule-form-ready'));
                    }
                }).catch(() => {});
            }
        });
    }
    updateCountdowns();
    setInterval(updateCountdowns, 1000);
    function prepareToasts() {
        document.querySelectorAll('.toast:not([data-ready])').forEach((toast) => {
            toast.dataset.ready = 'true';
            let timer;
            const dismiss = () => {
                clearTimeout(timer);
                if (toast.contains(document.activeElement)) {
                    const heading = document.querySelector('.page-content h1');
                    heading?.setAttribute('tabindex', '-1');
                    heading?.focus();
                }
                toast.classList.add('is-leaving');
                setTimeout(() => toast.remove(), 200);
            };
            const start = () => {
                clearTimeout(timer);
                if (!toast.matches(':hover') && !toast.contains(document.activeElement)) {
                    timer = setTimeout(dismiss, 8000);
                }
            };
            toast.addEventListener('pointerenter', () => clearTimeout(timer));
            toast.addEventListener('focusin', () => clearTimeout(timer));
            toast.addEventListener('pointerleave', start);
            toast.addEventListener('focusout', () => setTimeout(start, 0));
            toast.querySelector('.toast-close')?.addEventListener('click', dismiss);
            start();
        });
    }
    prepareToasts();
    document.addEventListener('click', (event) => {
        document.querySelectorAll('.capsule-menu[open]').forEach((menu) => {
            if (!menu.contains(event.target) || event.target.closest('a')) menu.open = false;
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('.capsule-menu[open]').forEach((menu) => {
            menu.open = false;
            menu.querySelector('summary').focus();
        });
    });
    const dialog = document.querySelector('#capsule-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const content = dialog.querySelector('.dialog-content');
    let opener;
    let busy = false;

    document.addEventListener('capsule-form-ready', () => {
        const heading = content.querySelector('h1');
        if (heading) heading.id = 'capsule-dialog-heading';
    });

    function focusHeading() {
        const heading = document.querySelector('.page-content h1');
        heading?.setAttribute('tabindex', '-1');
        heading?.focus();
    }

    function fill(html) {
        const page = new DOMParser().parseFromString(html, 'text/html');
        const surface = page.querySelector('.capsule-surface');
        if (!surface) throw new Error('Missing form');
        content.replaceChildren(surface);
        document.dispatchEvent(new Event('capsule-form-ready'));
        updateCountdowns();
    }

    document.addEventListener('click', async (event) => {
        const link = event.target.closest('[data-capsule-popup]');
        if (!link || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (busy) return;
        busy = true;
        if (!dialog.open) opener = link;
        try {
            const response = await fetch(link.href);
            if (!response.ok || response.redirected) throw new Error('Unavailable');
            fill(await response.text());
            dialog.showModal();
            // Keep destructive actions away from initial keyboard focus.
            (content.querySelector('[data-popup-cancel]') || dialog.querySelector('.dialog-close')).focus();
        } catch {
            window.location.assign(link.href);
        } finally {
            busy = false;
        }
    });

    dialog.addEventListener('click', (event) => {
        if (event.target.closest('.dialog-close, [data-popup-cancel]')) {
            event.preventDefault();
            if (!busy) dialog.close();
        }
        if (event.target === dialog && !busy) {
            const bounds = dialog.getBoundingClientRect();
            if (event.clientX < bounds.left || event.clientX > bounds.right ||
                event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
        }
    });
    dialog.addEventListener('cancel', (event) => {
        if (busy) event.preventDefault();
    });
    dialog.addEventListener('close', () => {
        content.replaceChildren();
        if (opener?.isConnected) opener.focus();
        else focusHeading();
    });
    dialog.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy) return;
        busy = true;
        const form = event.target;
        const button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
            const response = await fetch(form.action, {method: 'POST', body: new FormData(form)});
            if (response.redirected) {
                // Render the redirected page directly so Django's success message is preserved.
                const page = new DOMParser().parseFromString(await response.text(), 'text/html');
                if (page.querySelector('.capsule-reader, .capsule-photo-manager')) {
                    fill(page.documentElement.outerHTML);
                    content.querySelector('h1')?.setAttribute('tabindex', '-1');
                    content.querySelector('h1')?.focus();
                    const listing = await fetch(window.location.href);
                    if (listing.ok) {
                        const updated = new DOMParser().parseFromString(await listing.text(), 'text/html');
                        const collection = updated.querySelector('.collection-section');
                        if (collection) document.querySelector('.collection-section')?.replaceWith(collection);
                    }
                    return;
                }
                const main = page.querySelector('.page-content');
                if (!main) throw new Error('Missing page');
                dialog.close();
                document.querySelector('.page-content').replaceWith(main);
                const header = page.querySelector('.header-nav');
                if (header) document.querySelector('.header-nav').replaceWith(header);
                prepareToasts();
                window.history.replaceState(null, '', response.url);
                main.querySelector('h1')?.setAttribute('tabindex', '-1');
                main.querySelector('h1')?.focus();
            } else if (response.ok) {
                const selectedPhotos = Array.from(form.querySelector('[data-photo-input]')?.files || []);
                fill(await response.text());
                const photoInput = content.querySelector('[data-photo-input]');
                if (photoInput && selectedPhotos.length && typeof DataTransfer === 'function') {
                    const transfer = new DataTransfer();
                    selectedPhotos.forEach(file => transfer.items.add(file));
                    photoInput.files = transfer.files;
                    document.dispatchEvent(new Event('capsule-form-ready'));
                }
                const error = content.querySelector('.errorlist');
                error?.setAttribute('role', 'alert');
                const invalid = content.querySelector('[aria-invalid="true"]');
                if (invalid) invalid.focus();
                else if (error) {
                    error.setAttribute('tabindex', '-1');
                    error.focus();
                } else content.querySelector('input:not([type="hidden"]), textarea, select')?.focus();
            } else {
                throw new Error('Request failed');
            }
        } catch {
            let error = content.querySelector('.popup-error');
            if (!error) {
                error = document.createElement('p');
                error.className = 'popup-error errorlist';
                error.setAttribute('role', 'alert');
                form.append(error);
            }
            error.textContent = 'Nu am putut confirma operațiunea. Verifică lista capsulelor înainte să încerci din nou.';
            button.disabled = false;
        } finally {
            busy = false;
        }
    });
})();
