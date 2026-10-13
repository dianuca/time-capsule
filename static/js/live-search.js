(() => {
    let timer;
    let controller;
    let revision = 0;

    function invalidate() {
        clearTimeout(timer);
        controller?.abort();
        revision += 1;
    }

    async function search(form, state = form.elements.state.value) {
        invalidate();
        const current = revision;
        const collection = form.closest('.collection-section');
        const status = collection.querySelector('.search-status');
        const url = new URL(form.action);
        const query = form.elements.q.value.trim();
        url.searchParams.set('state', state);
        if (query) url.searchParams.set('q', query);
        else url.searchParams.delete('q');
        controller = new AbortController();
        collection.setAttribute('aria-busy', 'true');
        status.textContent = 'Se caută…';
        try {
            const response = await fetch(url, {signal: controller.signal});
            if (current !== revision || !collection.isConnected) return;
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error('Search failed');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            if (current !== revision || !collection.isConnected) return;
            const grid = page.querySelector('.capsule-grid');
            const filters = page.querySelector('.collection-filters');
            if (!grid || !filters) throw new Error('Missing results');
            const filtersFocused = collection.querySelector('.collection-filters').contains(document.activeElement);
            collection.querySelector('.capsule-grid').replaceWith(grid);
            collection.querySelector('.collection-filters').replaceWith(filters);
            form.elements.state.value = state;
            // Leave the input untouched so typing, selection and focus are preserved.
            form.querySelector('.search-reset')?.remove();
            const reset = page.querySelector('.search-reset');
            if (reset) form.append(reset);
            window.history.replaceState(null, '', url);
            status.textContent = `${grid.dataset.resultCount} capsule găsite.`;
            if (filtersFocused) filters.querySelector('[aria-current="page"]')?.focus();
        } catch (error) {
            if (current === revision && error.name !== 'AbortError' && collection.isConnected) {
                status.textContent = 'Căutarea nu a reușit. Încearcă din nou folosind lupa.';
            }
        } finally {
            if (current === revision) collection.removeAttribute('aria-busy');
        }
    }

    function schedule(event) {
        if (!event.target.matches('#capsule-search')) return;
        invalidate();
        event.target.closest('.collection-section').removeAttribute('aria-busy');
        if (event.isComposing) return;
        const form = event.target.form;
        timer = setTimeout(() => search(form), 300);
    }
    document.addEventListener('input', schedule);
    document.addEventListener('compositionend', schedule);
    document.addEventListener('submit', (event) => {
        if (!event.target.matches('.collection-search')) return;
        event.preventDefault();
        search(event.target);
    });
    document.addEventListener('click', (event) => {
        const link = event.target.closest('.collection-filter, .search-reset');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        const form = link.closest('.collection-section').querySelector('.collection-search');
        event.preventDefault();
        if (link.matches('.search-reset')) {
            form.elements.q.value = '';
            form.elements.q.focus();
        }
        search(form, new URL(link.href).searchParams.get('state') || 'all');
    });
})();
