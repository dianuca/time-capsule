const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const source = readFileSync(join(__dirname, '..', 'profile-avatar.js'), 'utf8');

function fixture(saved = '/accounts/avatar/') {
    function control(properties) {
        return {...properties, events: {}, addEventListener(name, handler) { this.events[name] = handler; }};
    }
    const revoked = [];
    let counter = 0;
    const input = control({files: [], focus() { this.focused = true; }});
    Object.defineProperty(input, 'value', {set(value) { if (value === '') this.files = []; }});
    const image = control({src: saved, dataset: {savedAvatar: saved}, getAttribute() { return this.src; }, removeAttribute() { this.src = null; }});
    const fallback = {hidden: !!saved};
    const remove = control({checked: false});
    const reset = control({hidden: true});
    const nodes = {'#id_avatar_upload': input, '[data-avatar-image]': image, '[data-avatar-default]': fallback, '#id_remove_avatar': remove, '[data-avatar-reset]': reset};
    runInNewContext(source, {
        document: {querySelector: selector => nodes[selector]},
        URL: {createObjectURL: () => `blob:${++counter}`, revokeObjectURL: url => revoked.push(url)},
        window: {addEventListener() {}},
    });
    return {input, image, fallback, remove, reset, revoked};
}

test('initialization preserves the saved photograph or displays the default avatar', () => {
    const saved = fixture();
    assert.equal(saved.image.src, '/accounts/avatar/');
    assert.equal(saved.image.hidden, false);
    assert.equal(saved.fallback.hidden, true);
    const empty = fixture(null);
    assert.equal(empty.image.hidden, true);
    assert.equal(empty.fallback.hidden, false);
});

test('selection previews the new file and reset restores the original without saving', () => {
    const f = fixture();
    f.remove.checked = true;
    f.input.files = [{name: 'portrait.png'}];
    f.input.events.change();
    assert.equal(f.image.src, 'blob:1');
    assert.equal(f.remove.checked, false);
    assert.equal(f.reset.hidden, false);
    f.reset.events.click();
    assert.equal(f.input.files.length, 0);
    assert.equal(f.image.src, '/accounts/avatar/');
    assert.deepEqual(f.revoked, ['blob:1']);
});

test('removal previews the default and can be undone before save', () => {
    const f = fixture();
    f.remove.checked = true;
    f.remove.events.change();
    assert.equal(f.image.hidden, true);
    assert.equal(f.fallback.hidden, false);
    f.remove.checked = false;
    f.remove.events.change();
    assert.equal(f.image.src, '/accounts/avatar/');
    assert.equal(f.image.hidden, false);
});
