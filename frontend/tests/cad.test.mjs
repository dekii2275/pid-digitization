import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cadKind } from '../src/services/cad.js';

test('CAD preview distinguishes the four symbol classes on drawing 304', () => {
  for (const [label_id, expected] of [
    ['LC-001', 'connector'],
    ['VALVES-012', 'check_valve'],
    ['VALVES-019', 'valve'],
    ['VALVES-020', 'globe_valve'],
  ]) {
    const type = label_id === 'LC-001' ? 'PROCESS/INSTRUMENT SIGNAL LINE WITHIN A UNIT' : 'VALVE';
    assert.equal(cadKind({ label_id, type }), expected);
  }
});

test('CAD preview preserves manual shape choices and handles AI names without library codes', () => {
  assert.equal(cadKind({ label_id: 'LC-001', cad_kind: 'other' }), 'other');
  assert.equal(cadKind({ type: 'GLOBE VALVE' }), 'globe_valve');
  assert.equal(cadKind({ type: 'CHECK VALVE' }), 'check_valve');
  assert.equal(cadKind({ type: 'Pressure transmitter' }), 'instrument');
  assert.equal(cadKind({ type: 'Centrifugal pump' }), 'pump');
  assert.equal(cadKind({ label_id: null }), 'other');
});
