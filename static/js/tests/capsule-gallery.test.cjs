const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const source = readFileSync(join(__dirname, '..', 'capsule-gallery.js'), 'utf8');

function galleryFixture(count) {
    const stageEvents = {}, galleryEvents = {};
    const slides = Array.from({length: count}, () => ({hidden: false, setAttribute() {}}));
    const current = {textContent: ''};
    const counter = {setAttribute(name, value) { this[name] = value; }};
    const arrows = {hidden: true}, footer = {hidden: true};
    const stage = {setAttribute() {}, addEventListener(name, fn) { stageEvents[name] = fn; }};
    const gallery = {
        nodeType: 1, dataset: {}, setAttribute() {},
        matches: selector => selector === '.capsule-photo-gallery',
        querySelectorAll: selector => selector === '.capsule-gallery-slide' ? slides : [],
        querySelector: selector => ({
            '.capsule-gallery-stage': stage, '[data-gallery-current]': current,
            '.capsule-gallery-counter': counter, '.capsule-gallery-arrows': arrows,
            '.capsule-gallery-footer': footer,
        }[selector]),
        addEventListener(name, fn) { galleryEvents[name] = fn; },
    };
    return {
        gallery, slides, current, counter, arrows, footer, stage,
        click(direction) { galleryEvents.click({target: {closest: () => ({dataset: {galleryDirection: String(direction)}})}}); },
        key(key, modifiers = {}) {
            const event = {key, ...modifiers, prevented: false, preventDefault() { this.prevented = true; }};
            stageEvents.keydown(event);
            return event;
        },
        swipe(dx, dy = 0) {
            stageEvents.touchstart({touches: [{clientX: 100, clientY: 100}]});
            stageEvents.touchend({changedTouches: [{clientX: 100 + dx, clientY: 100 + dy}]});
        },
    };
}

function boot(fixture) {
    let onMutation;
    runInNewContext(source, {
        document: {body: {nodeType: 1, matches: () => false, querySelectorAll: () => [fixture.gallery]}},
        MutationObserver: class {
            constructor(callback) { onMutation = callback; }
            observe() {}
        },
    });
    return root => onMutation([{addedNodes: [root]}]);
}

test('shows one photo with a correct counter and wraps through arrows', () => {
    const fixture = galleryFixture(3);
    boot(fixture);
    assert.deepEqual(fixture.slides.map(slide => slide.hidden), [false, true, true]);
    assert.equal(fixture.current.textContent, 1);
    assert.equal(fixture.counter['aria-label'], 'Fotografia 1 din 3');
    fixture.click(-1);
    assert.equal(fixture.current.textContent, 3);
    fixture.click(1);
    assert.equal(fixture.current.textContent, 1);
    fixture.click(1);
    assert.deepEqual(fixture.slides.map(slide => slide.hidden), [true, false, true]);
});

test('keyboard navigation supports arrows, Home and End without capturing shortcuts', () => {
    const fixture = galleryFixture(4);
    boot(fixture);
    assert.equal(fixture.key('ArrowRight').prevented, true);
    assert.equal(fixture.current.textContent, 2);
    fixture.key('End');
    assert.equal(fixture.current.textContent, 4);
    fixture.key('Home');
    assert.equal(fixture.current.textContent, 1);
    fixture.key('ArrowLeft');
    assert.equal(fixture.current.textContent, 4);
    assert.equal(fixture.key('ArrowRight', {ctrlKey: true}).prevented, false);
    assert.equal(fixture.current.textContent, 4);
});

test('horizontal swipes navigate while vertical scrolling and short gestures do not', () => {
    const fixture = galleryFixture(3);
    boot(fixture);
    fixture.swipe(-80);
    assert.equal(fixture.current.textContent, 2);
    fixture.swipe(80);
    assert.equal(fixture.current.textContent, 1);
    fixture.swipe(-15);
    fixture.swipe(-50, 100);
    assert.equal(fixture.current.textContent, 1);
});

test('a single photo displays 1/1 and hides the arrows', () => {
    const fixture = galleryFixture(1);
    boot(fixture);
    assert.equal(fixture.arrows.hidden, true);
    assert.equal(fixture.footer.hidden, false);
    assert.equal(fixture.current.textContent, 1);
    assert.equal(fixture.slides[0].hidden, false);
});

test('galleries inserted into a modal initialize independently and only once', () => {
    const first = galleryFixture(2);
    const insert = boot(first);
    first.click(1);
    const second = galleryFixture(3);
    insert(second.gallery);
    second.click(1);
    insert(second.gallery);
    assert.equal(first.current.textContent, 2);
    assert.equal(second.current.textContent, 2);
    insert({nodeType: 3});
});
