'use strict';

const assert = require('node:assert/strict');
const {test} = require('node:test');
const {runJourney, sessionForExecution} = require('./journey');

function fixture(responses) {
  const calls = [];
  const messages = [];
  const logger = {
    info: (event, fields) => messages.push({event, ...fields}),
    error: (event, fields) => messages.push({event, ...fields}),
  };
  const get = async (path, headers, timeout) => {
    calls.push({path, headers, timeout});
    const response = responses.shift();
    if (response instanceof Error) throw response;
    return response;
  };
  return {calls, messages, logger, get, traceId: '1'.repeat(32), executionId: 'test-execution'};
}

const home = {status: 200, body: '<a href="/product/OLJCESPC7Z">product</a>'};
const detail = {status: 200, body: '<input value="OLJCESPC7Z">'};
const cart = {status: 200, body: 'Your shopping cart is empty!'};

test('three scoped reads, isolated cookie, bounded requests and cleanup', async () => {
  const f = fixture([home, detail, cart]);
  await runJourney(f);
  assert.deepEqual(f.calls.map(c => c.path), ['/', '/product/OLJCESPC7Z', '/cart']);
  assert(f.calls.every(c => c.timeout > 0 && c.timeout <= 8000));
  assert(f.calls.every(c => c.headers.Cookie === f.calls[0].headers.Cookie));
  assert.equal(f.calls[0].headers.Cookie, 'shop_session-id=' + sessionForExecution(f.executionId));
  assert.equal(f.messages.at(-1).event, 'synthetic.cleanup');
  assert.equal(f.messages.at(-1).redis_writes, 0);
  assert(f.messages.at(-1).local_session_discarded);
  assert(!JSON.stringify(f.messages).includes(f.calls[0].headers.Cookie));
});

test('partial network or HTTP failure always cleans local session without retry', async () => {
  for (const failure of [new Error('timeout'), {status: 500, body: 'private'}, {status: 302, body: ''}]) {
    const f = fixture([home, failure]);
    await assert.rejects(runJourney(f), /shop_product_failed/);
    assert.equal(f.calls.length, 2);
    assert.equal(f.messages.at(-1).event, 'synthetic.cleanup');
    assert(!JSON.stringify(f.messages).includes('private'));
  }
});

test('invalid catalog, nonempty cart and expired budget fail closed', async () => {
  for (const [responses, count] of [
    [[{status: 200, body: '<a href="https://foreign.invalid/product/id">bad</a>'}], 1],
    [[home, detail, {status: 200, body: 'cart has state'}], 3],
  ]) {
    const f = fixture(responses);
    await assert.rejects(runJourney(f));
    assert.equal(f.calls.length, count);
    assert.equal(f.messages.at(-1).event, 'synthetic.cleanup');
  }
  const f = fixture([home]);
  let ticks = 0;
  f.now = () => ticks++ === 0 ? 0 : 30001;
  await assert.rejects(runJourney(f), /shop_catalog_failed/);
  assert.equal(f.calls.length, 0);
  assert.equal(f.messages.at(-1).event, 'synthetic.cleanup');
});

test('trace attribution required before network activity and sessions are unique', async () => {
  const bad = fixture([]);
  bad.traceId = undefined;
  await assert.rejects(runJourney(bad), /synthetic_trace_context_missing/);
  assert.equal(bad.calls.length, 0);
  const first = fixture([home, detail, cart]);
  const second = fixture([home, detail, cart]);
  second.executionId = 'another-execution';
  await runJourney(first);
  await runJourney(second);
  assert.notEqual(first.calls[0].headers.Cookie, second.calls[0].headers.Cookie);
  assert.throws(() => sessionForExecution(undefined), /synthetic_execution_id_missing/);
});
