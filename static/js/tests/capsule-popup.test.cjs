const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const source = readFileSync(join(__dirname, '..', 'capsules.js'), 'utf8');

function fixture() {
    let focused;
    function node(properties = {}) {
        return {events: {}, attrs: {}, isConnected: true, ...properties,
            addEventListener(name, handler) { (this.events[name] ||= []).push(handler); },
            setAttribute(name, value) { this.attrs[name] = value; },
            focus() { focused = this; },
        };
    }
    const heading = node({id: 'capsule-heading'});
    const backgroundHeading = node({id: 'capsule-heading'});
    const close = node();
    const invalid = node();
    const error = node();
    let currentSurface;
    const surface = (hasInvalid = false, hasError = false) => node({querySelector(selector) {
        if (selector === 'h1') return heading;
        if (selector === '[aria-invalid="true"]') return hasInvalid ? invalid : null;
        if (selector === '.errorlist') return hasError ? error : null;
        return null;
    }});
    const content = node({
        querySelector(selector) { return currentSurface?.querySelector(selector) || null; },
        replaceChildren(next) { currentSurface = next; },
    });
    const dialog = node({open: false,
        querySelector(selector) { return selector === '.dialog-content' ? content : close; },
        showModal() { this.open = true; },
        close() { this.open = false; this.events.close.forEach(handler => handler()); },
    });
    const document = node({querySelectorAll() { return []; },
        querySelector(selector) { return selector === '#capsule-dialog' ? dialog : backgroundHeading; },
        dispatchEvent(event) { (this.events[event.type] || []).forEach(handler => handler(event)); },
    });
    let nextSurface = surface();
    let requests = 0;
    runInNewContext(source, {
        document,
        window: {location: {assign() { throw Error('unexpected navigation'); }}},
        fetch: async () => { requests++; return {ok: true, redirected: false, text: async () => 'page'}; },
        DOMParser: class { parseFromString() { return {querySelector() { return nextSurface; }}; } },
        Event: class { constructor(type) { this.type = type; } },
        FormData: class {}, setInterval() {}, setTimeout() {}, clearTimeout() {},
    });
    function link() { return node({href: '/form/', closest(selector) { return selector === '[data-capsule-popup]' ? this : null; }}); }
    async function open(opener, properties = {}) {
        const event = {target: opener, preventDefault() {}, ...properties};
        for (const handler of document.events.click) await handler(event);
    }
    async function submit(hasInvalid, hasError) {
        nextSurface = surface(hasInvalid, hasError);
        const submitButton = node();
        const form = node({action: '/form/', querySelector(selector) { return selector === '[type="submit"]' ? submitButton : null; }});
        await dialog.events.submit[0]({target: form, preventDefault() {}});
    }
    return {heading, backgroundHeading, close, invalid, error, dialog, link, open, submit,
        focused: () => focused, requests: () => requests};
}

test('modal uses a separate heading ID and starts focus on its close control', async () => {
    const f = fixture();
    await f.open(f.link());
    assert.equal(f.heading.id, 'capsule-dialog-heading');
    assert.equal(f.backgroundHeading.id, 'capsule-heading');
    assert.equal(f.focused(), f.close);
});

test('closing after navigation inside a modal restores the original page opener', async () => {
    const f = fixture();
    const original = f.link();
    await f.open(original);
    await f.open(f.link());
    f.dialog.close();
    assert.equal(f.focused(), original);
});

test('closing restores focus to the page heading when the opener was removed', async () => {
    const f = fixture();
    const original = f.link();
    await f.open(original);
    original.isConnected = false;
    f.dialog.close();
    assert.equal(f.focused(), f.backgroundHeading);
    assert.equal(f.backgroundHeading.attrs.tabindex, '-1');
});

test('validation puts focus on the invalid field instead of an earlier valid input', async () => {
    const f = fixture();
    await f.open(f.link());
    await f.submit(true, true);
    assert.equal(f.focused(), f.invalid);
    assert.equal(f.error.attrs.role, 'alert');
});

test('non-field validation errors receive focus when no input is invalid', async () => {
    const f = fixture();
    await f.open(f.link());
    await f.submit(false, true);
    assert.equal(f.focused(), f.error);
    assert.equal(f.error.attrs.tabindex, '-1');
});

test('modified clicks preserve native navigation without fetching a modal', async () => {
    const f = fixture();
    for (const properties of [{button: 1}, {ctrlKey: true}, {metaKey: true}, {shiftKey: true}, {altKey: true}]) {
        await f.open(f.link(), properties);
    }
    assert.equal(f.requests(), 0);
    assert.equal(f.dialog.open, false);
});
