(() => {
    const urls = new Map();
    const selections = new WeakMap();
    function releaseUnused() {
        for (const [input, references] of urls) {
            if (!input.isConnected) {
                references.forEach(url => URL.revokeObjectURL(url));
                urls.delete(input);
            }
        }
    }
    function render(form) {
        const input = form.querySelector('[data-photo-input]');
        if (!input) return;
        selections.set(input, Array.from(input.files));
        const previews = form.querySelector('.new-photo-previews');
        urls.get(input)?.forEach(url => URL.revokeObjectURL(url));
        const references = [];
        urls.set(input, references);
        previews.replaceChildren();
        Array.from(input.files).forEach((file, index) => {
            const card = document.createElement('figure');
            card.className = 'new-photo-preview';
            const image = document.createElement('img');
            if (/^image\/(jpeg|png|webp)$/.test(file.type)) {
                const url = URL.createObjectURL(file);
                references.push(url);
                image.src = url;
            }
            image.alt = file.name;
            card.title = file.name;
            card.append(image);
            if (typeof DataTransfer === 'function') {
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.textContent = '×';
                remove.setAttribute('aria-label', `Renunță la ${file.name}`);
                remove.addEventListener('click', () => {
                    const transfer = new DataTransfer();
                    Array.from(input.files).forEach((selected, selectedIndex) => {
                        if (selectedIndex !== index) transfer.items.add(selected);
                    });
                    input.files = transfer.files;
                    render(form);
                    input.focus();
                });
                card.append(remove);
            }
            previews.append(card);
        });
        const kept = form.querySelectorAll('.photo-choice input:not(:checked)').length;
        form.querySelector('[data-photo-count]').textContent = `${kept + input.files.length}/10`;
    }
    document.addEventListener('change', event => {
        if (!event.target.matches('[data-photo-input], .photo-choice input')) return;
        if (event.target.matches('[data-photo-input]') && typeof DataTransfer === 'function') {
            const transfer = new DataTransfer();
            const seen = new Set();
            [...(selections.get(event.target) || []), ...event.target.files].forEach(file => {
                const key = `${file.name}/${file.size}/${file.lastModified}/${file.type}`;
                if (!seen.has(key)) {
                    transfer.items.add(file);
                    seen.add(key);
                }
            });
            event.target.files = transfer.files;
        }
        render(event.target.form);
    });
    document.addEventListener('capsule-form-ready', () => {
        releaseUnused();
        document.querySelectorAll('.capsule-editor-form').forEach(render);
    });
    document.querySelectorAll('.capsule-editor-form').forEach(render);
    new MutationObserver(releaseUnused).observe(document.body, {childList: true, subtree: true});
})();
