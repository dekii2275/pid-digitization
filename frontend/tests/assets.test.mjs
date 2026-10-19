import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import {
  assetCreatePayload,
  createAsset,
  linkOccurrence,
  occurrenceLinkIssue,
} from '../src/services/assets.js';

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

const profile = {
  project: 'HaNoi',
  area: 'HN',
  tag: 'xy-10',
  name: 'MAY NO',
  equipment_type: 'GATE VALVE',
  notes: '',
};
const position = {
  drawing_id: 'a'.repeat(32),
  page_number: 1,
  source: 'annotation',
  kind: 'symbol',
  item_id: 's1',
  generation: '',
  tag: '',
  project: '',
  symbol_code: 'VALVES-019',
};

test('creating independently sends the profile without a drawing link', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/assets');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), profile);
    return Response.json({ id: 'created', ...profile }, { status: 201 });
  };
  const result = await createAsset(assetCreatePayload(profile, position, false));
  assert.equal(result.tag, 'xy-10');
});

test('the form can explicitly link an untagged symbol without changing its source tag or project', () => {
  const payload = assetCreatePayload(profile, position, true);
  assert.equal(payload.tag, 'xy-10');
  assert.equal(payload.occurrence.tag, '');
  assert.equal(payload.occurrence.symbol_code, 'VALVES-019');
  assert.equal(Object.hasOwn(payload.occurrence, 'project'), false);
  assert.equal(occurrenceLinkIssue(position, profile.project), '');
});

test('a drawing without a project can be linked manually to a profile with a project', () => {
  const source = { ...position, tag: 'V-101' };
  assert.equal(occurrenceLinkIssue(source, profile.project), '');
  assert.equal(assetCreatePayload(profile, source, true).occurrence.tag, 'V-101');
  assert.deepEqual(assetCreatePayload(profile, source, false), profile);
});

test('linking an existing profile includes the stable symbol identity', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/assets/existing/occurrences');
    const body = JSON.parse(options.body);
    assert.equal(body.tag, '');
    assert.equal(body.symbol_code, 'VALVES-019');
    assert.equal(body.item_id, 's1');
    assert.equal(Object.hasOwn(body, 'project'), false);
    return Response.json({ linked: true }, { status: 201 });
  };
  assert.deepEqual(await linkOccurrence('existing', position), { linked: true });
});

test('empty OCR and missing source identity cannot be used for manual links', () => {
  assert.match(occurrenceLinkIssue(null, profile.project), /Chọn một vị trí/);
  assert.throws(
    () => assetCreatePayload(profile, { ...position, kind: 'text' }, true),
    /Chọn một symbol/,
  );
  assert.throws(
    () => assetCreatePayload(profile, { ...position, symbol_code: '' }, true),
    /Chọn một symbol/,
  );
});

test('an explicit link preserves the saved source tag and normalizes project comparison', () => {
  const source = { ...position, project: ' hanoi ', tag: 'V-101' };
  const payload = assetCreatePayload(profile, source, true);
  assert.equal(payload.tag, 'xy-10');
  assert.equal(payload.occurrence.tag, 'V-101');
  assert.equal(payload.occurrence.item_id, 's1');
  assert.equal(Object.hasOwn(payload.occurrence, 'project'), false);
  assert.equal(payload.occurrence.symbol_code, 'VALVES-019');
});

test('changing the project requires correcting it or explicitly opting out of the link', () => {
  const source = { ...position, project: 'Plant B', tag: 'V-101' };
  assert.throws(() => assetCreatePayload(profile, source, true), /Dự án.*phải trùng/);
  assert.deepEqual(assetCreatePayload(profile, source, false), profile);
});

test('FastAPI validation arrays identify the field instead of hiding the 422 error', async () => {
  globalThis.fetch = async () =>
    Response.json(
      {
        detail: [
          {
            type: 'string_too_short',
            loc: ['body', 'occurrence', 'tag'],
            msg: 'String should have at least 1 character',
          },
        ],
      },
      { status: 422 },
    );
  await assert.rejects(createAsset(profile), (error) => {
    assert.equal(error.status, 422);
    assert.match(error.message, /Tag tại vị trí trên bản vẽ: không được để trống/);
    return true;
  });
});

test('duplicate and project errors returned by the server retain their explanation', async () => {
  globalThis.fetch = async () =>
    Response.json({ detail: 'Tag đã có hồ sơ trong dự án/khu vực này.' }, { status: 409 });
  await assert.rejects(createAsset(profile), /Tag đã có hồ sơ trong dự án\/khu vực này/);
});
