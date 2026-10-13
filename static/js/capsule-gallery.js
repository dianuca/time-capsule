(() => {
    function initialize(gallery) {
        if (gallery.dataset.ready) return;
        const slides = Array.from(gallery.querySelectorAll('.capsule-gallery-slide'));
        if (!slides.length) return;
        gallery.dataset.ready = 'true';
        gallery.setAttribute('aria-roledescription', 'carusel');
        const stage = gallery.querySelector('.capsule-gallery-stage');
        const current = gallery.querySelector('[data-gallery-current]');
        const counter = gallery.querySelector('.capsule-gallery-counter');
        gallery.querySelector('.capsule-gallery-footer').hidden = false;
        gallery.querySelector('.capsule-gallery-arrows').hidden = slides.length < 2;
        if (slides.length > 1) {
            stage.tabIndex = 0;
            stage.setAttribute('aria-label', 'Galerie foto. Folosește săgețile stânga și dreapta pentru navigare.');
        }
        let index = 0;
        let touchStart;
        function show(next) {
            index = (next + slides.length) % slides.length;
            slides.forEach((slide, position) => {
                slide.hidden = position !== index;
                slide.setAttribute('role', 'group');
                slide.setAttribute('aria-label', `${position + 1} din ${slides.length}`);
            });
            current.textContent = index + 1;
            counter.setAttribute('aria-label', `Fotografia ${index + 1} din ${slides.length}`);
        }
        gallery.addEventListener('click', event => {
            const button = event.target.closest('[data-gallery-direction]');
            if (button) show(index + Number(button.dataset.galleryDirection));
        });
        stage.addEventListener('keydown', event => {
            if (event.altKey || event.ctrlKey || event.metaKey) return;
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault();
                show(index + (event.key === 'ArrowRight' ? 1 : -1));
            } else if (event.key === 'Home' || event.key === 'End') {
                event.preventDefault();
                show(event.key === 'Home' ? 0 : slides.length - 1);
            }
        });
        stage.addEventListener('touchstart', event => {
            touchStart = event.touches.length === 1 ? {x: event.touches[0].clientX, y: event.touches[0].clientY} : null;
        }, {passive: true});
        stage.addEventListener('touchend', event => {
            if (!touchStart || !event.changedTouches.length) return;
            const dx = event.changedTouches[0].clientX - touchStart.x;
            const dy = event.changedTouches[0].clientY - touchStart.y;
            if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.5) show(index + (dx < 0 ? 1 : -1));
            touchStart = null;
        }, {passive: true});
        stage.addEventListener('touchcancel', () => { touchStart = null; }, {passive: true});
        show(0);
    }
    function discover(root) {
        if (root.nodeType !== 1) return;
        if (root.matches('.capsule-photo-gallery')) initialize(root);
        root.querySelectorAll('.capsule-photo-gallery').forEach(initialize);
    }
    discover(document.body);
    new MutationObserver(records => {
        records.forEach(record => record.addedNodes.forEach(discover));
    }).observe(document.body, {childList: true, subtree: true});
})();
