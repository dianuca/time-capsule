const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const source = readFileSync(join(__dirname, '..', 'live-search.js'), 'utf8');

function fixture() {
    const events = {}, timers = new Map(), requests = [], replaced = [];
    let nextTimer = 0, currentUrl, scrolled = false;
    const document = {addEventListener(name, handler) { events[name] = handler; }};
    const status = {textContent: ''};
    const nodes = Object.fromEntries(['.capsule-grid', '.collection-filters', '.collection-pagination'].map(selector => [selector, {
        replaceWith(node) { replaced.push(selector); nodes[selector] = node; },
        contains: () => false,
    }]));
    const collection = {
        isConnected: true, setAttribute() {}, removeAttribute() {},
        querySelector: selector => selector === '.search-status' ? status : selector === '.collection-search' ? form : nodes[selector],
    };
    const input = {value: 'mare & cer', matches: selector => selector === '#capsule-search', closest: () => collection, focus() { document.activeElement = this; }};
    const form = {action: 'http://localhost/capsules/?page=3', elements: {q: input, state: {value: 'draft'}}, closest: () => collection, querySelector: () => null, append() {}};
    input.form = form;
    input.focus();
    class Parser {
        parseFromString(text) {
            const data = JSON.parse(text);
            const fresh = {
                '.capsule-grid': {dataset: {resultCount: data.total, pageNumber: data.page, pageCount: data.pages}, focus() { document.activeElement = this; }, scrollIntoView() { scrolled = true; }},
                '.collection-filters': {contains: () => false, querySelector: () => null},
                '.collection-pagination': {},
            };
            for (const [selector, node] of Object.entries(fresh)) node.replaceWith = replacement => { replaced.push(selector); nodes[selector] = replacement; };
            return {querySelector: selector => fresh[selector] || null};
        }
    }
    runInNewContext(source, {
        document, URL, AbortController, DOMParser: Parser,
        setTimeout(fn) { timers.set(++nextTimer, fn); return nextTimer; }, clearTimeout(id) { timers.delete(id); },
        fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); },
        window: {history: {replaceState(_state, _title, url) { currentUrl = url; }}, location: {assign() { throw new Error('Unexpected navigation'); }}},
    });
    return {
        input, form, requests, replaced, document, nodes, status,
        get currentUrl() { return currentUrl; }, get scrolled() { return scrolled; },
        type(value) { input.value = value; events.input({target: input}); },
        flush() { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); },
        click(type, query = 'mare & cer', state = 'draft', page = 2) {
            const href = `http://localhost/capsules/?${new URLSearchParams({q: query, state, page})}`;
            const link = {href, matches: selector => selector === type, closest: () => collection};
            events.click({target: {closest: () => link}, button: 0, preventDefault() {}});
        },
        async respond(index, page = 1, total = 25, pages = 3) {
            requests[index].resolve({ok: true, redirected: false, text: async () => JSON.stringify({page: String(page), total: String(total), pages: String(pages)})});
            await new Promise(resolve => setImmediate(resolve));
        },
    };
}

test('typing resets pagination and updates all result sections without losing input focus', async () => {
    const f = fixture();
    f.type('mare'); f.type('mare & cer');
    assert.equal(f.requests.length, 0);
    f.flush();
    assert.equal(f.requests.length, 1);
    assert.equal(f.requests[0].url.searchParams.get('page'), '1');
    assert.equal(f.requests[0].url.searchParams.get('state'), 'draft');
    await f.respond(0);
    assert.deepEqual(f.replaced, ['.capsule-grid', '.collection-filters', '.collection-pagination']);
    assert.equal(f.document.activeElement, f.input);
    assert.equal(f.input.value, 'mare & cer');
    assert.match(f.status.textContent, /25 capsule/);
});

test('page navigation preserves query and filter and moves focus to the new results', async () => {
    const f = fixture();
    f.click('.collection-page-link');
    assert.equal(f.requests[0].url.searchParams.get('page'), '2');
    assert.equal(f.requests[0].url.searchParams.get('q'), 'mare & cer');
    assert.equal(f.requests[0].url.searchParams.get('state'), 'draft');
    await f.respond(0, 2);
    assert.equal(f.currentUrl.searchParams.get('page'), '2');
    assert.equal(f.document.activeElement, f.nodes['.capsule-grid']);
    assert.equal(f.scrolled, true);
});

test('filter changes and resetting the query return to page one', async () => {
    const f = fixture();
    f.click('.collection-filter', 'mare & cer', 'sealed', 3);
    assert.equal(f.requests[0].url.searchParams.get('page'), '1');
    await f.respond(0, 1, 7, 1);
    f.click('.search-reset', '', 'sealed', 3);
    assert.equal(f.requests[1].url.searchParams.get('page'), '1');
    assert.equal(f.requests[1].url.searchParams.has('q'), false);
    assert.equal(f.input.value, '');
    assert.equal(f.document.activeElement, f.input);
});

test('the URL uses the actual server page when a requested page no longer exists', async () => {
    const f = fixture();
    f.click('.collection-page-link', 'mare & cer', 'draft', 99);
    await f.respond(0, 2, 24, 2);
    assert.equal(f.currentUrl.searchParams.get('page'), '2');
});

test('old page responses are ignored as soon as a new search is typed', async () => {
    const f = fixture();
    f.click('.collection-page-link');
    f.type('nou');
    assert.equal(f.requests[0].options.signal.aborted, true);
    await f.respond(0, 2);
    assert.deepEqual(f.replaced, []);
    f.flush();
    await f.respond(1, 1, 0, 1);
    assert.equal(f.currentUrl.searchParams.get('q'), 'nou');
    assert.equal(f.currentUrl.searchParams.get('page'), '1');
});

test('a page click while the query is being changed starts the new search on page one', () => {
    const f = fixture();
    f.type('altceva');
    f.click('.collection-page-link');
    assert.equal(f.requests[0].url.searchParams.get('q'), 'altceva');
    assert.equal(f.requests[0].url.searchParams.get('page'), '1');
});
