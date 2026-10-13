(() => {
    const dialog = document.querySelector('#capsule-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const content = dialog.querySelector('.dialog-content');
    let opener;
    let busy = false;

    function fill(html) {
        const page = new DOMParser().parseFromString(html, 'text/html');
        const surface = page.querySelector('.capsule-surface');
        if (!surface) throw new Error('Missing form');
        content.replaceChildren(surface);
    }

    document.addEventListener('click', async (event) => {
        const link = event.target.closest('[data-capsule-popup]');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (busy) return;
        busy = true;
        opener = link;
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
        opener?.focus();
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
                const main = page.querySelector('.page-content');
                if (!main) throw new Error('Missing page');
                dialog.close();
                document.querySelector('.page-content').replaceWith(main);
                window.history.replaceState(null, '', response.url);
                main.querySelector('h1')?.setAttribute('tabindex', '-1');
                main.querySelector('h1')?.focus();
            } else if (response.ok) {
                fill(await response.text());
                content.querySelector('.errorlist')?.setAttribute('role', 'alert');
                content.querySelector('input, textarea')?.focus();
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
