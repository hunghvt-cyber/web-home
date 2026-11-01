import {test} from 'node:test';
import assert from 'node:assert/strict';
import {findDuplicates} from '../public/duplicate-core.js';
const a = 'a'.repeat(32), b = 'b'.repeat(32);
const file = (Path, hash = a, Size = 10, ID = Path) => ({Path, Size, ID, Hashes: {MD5: hash}});
test('same content, different names; identical names alone do not match', () => {
  const result = findDuplicates([file('one.jpg'), file('copy/two.jpg'), file('other/one.jpg', b)]);
  assert.equal(result.groups.length, 1); assert.equal(result.reclaimable, 10);
  assert.equal(result.groups[0].files.length, 2);
});
test('missing hash, different size and repeated inventory IDs do not create false copies', () => {
  const result = findDuplicates([file('a'), file('a-again', a, 10, 'a'), file('b', a, 20), file('c', ''), {Path:'d',Size:-1,Hashes:{MD5:a}}]);
  assert.equal(result.groups.length, 0); assert.equal(result.skipped, 3);
});
test('each scan is isolated; hashes must have the same algorithm', () => {
  assert.equal(findDuplicates([file('drive')]).groups.length, 0);
  assert.equal(findDuplicates([file('koofr')]).groups.length, 0);
  assert.equal(findDuplicates([file('a'), {Path:'b', Size:10, Hashes:{SHA256:a.repeat(2)}}]).groups.length, 0);
  assert.throws(() => findDuplicates({files: []}));
});
test('duplicate Drive paths with distinct IDs remain distinct files', () => {
  assert.equal(findDuplicates([file('same', a, 10, '1'), file('same', a, 10, '2')]).groups.length, 1);
});
