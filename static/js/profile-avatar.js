(() => {
    const input = document.querySelector('#id_avatar_upload');
    if (!input) return;
    const image = document.querySelector('[data-avatar-image]');
    const fallback = document.querySelector('[data-avatar-default]');
    const remove = document.querySelector('#id_remove_avatar');
    const reset = document.querySelector('[data-avatar-reset]');
    let preview;
    function render() {
        if (preview) URL.revokeObjectURL(preview);
        preview = null;
        const file = input.files[0];
        const saved = remove?.checked ? null : image.dataset.savedAvatar;
        if (file) preview = URL.createObjectURL(file);
        const source = preview || saved;
        image.hidden = !source;
        fallback.hidden = !!source;
        if (source) {
            if (image.getAttribute('src') !== source) image.src = source;
        } else {
            image.removeAttribute('src');
        }
        reset.hidden = !file;
    }
    input.addEventListener('change', () => {
        if (input.files.length && remove) remove.checked = false;
        render();
    });
    remove?.addEventListener('change', () => {
        if (remove.checked) input.value = '';
        render();
    });
    reset.addEventListener('click', () => {
        input.value = '';
        render();
        input.focus();
    });
    image.addEventListener('error', () => { image.hidden = true; fallback.hidden = false; });
    render();
    window.addEventListener('pageshow', render);
    window.addEventListener('pagehide', () => { if (preview) URL.revokeObjectURL(preview); });
})();
