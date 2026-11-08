'use strict';

const assert = require('node:assert/strict');
const {test} = require('node:test');
const {spawn} = require('node:child_process');
const http = require('node:http');
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');
const {once} = require('node:events');
const {sessionForExecution} = require('./journey');

for (const disableHttpInstrumentation of [false, true]) {
test('real Functions Framework HTTP invocation: active context and HTTPS correlation; HTTP hook disabled=' + disableHttpInstrumentation,
  {timeout: 30000}, async t => {
    const requests = [];
    let failProduct = false;
    const fixture = path.join(__dirname, 'test');
    const upstream = https.createServer({
      key: fs.readFileSync(path.join(fixture, 'tls-key.pem')),
      cert: fs.readFileSync(path.join(fixture, 'tls-cert.pem')),
    }, (req, res) => {
      requests.push({path: req.url, headers: req.headers});
      if (failProduct && req.url.startsWith('/product/')) res.statusCode = 500;
      res.end(req.url === '/' ? '<a href="/product/P1">product</a>' :
        req.url === '/product/P1' ? 'P1' : 'Your shopping cart is empty!');
    });
    await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
    t.after(() => new Promise(resolve => upstream.close(resolve)));
    const probe = http.createServer();
    await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
    const port = probe.address().port;
    await new Promise(resolve => probe.close(resolve));
    const main = path.join(path.dirname(require.resolve('@google-cloud/functions-framework')), 'main.js');
    const child = spawn(process.execPath, ['--require', path.join(fixture, 'entrypoint-preload.cjs'),
      main, '--source=' + __dirname, '--target=SyntheticFunction', '--port=' + port], {
      env: {...process.env, GOOGLE_CLOUD_PROJECT: 'local-sdk-proof',
        NODE_EXTRA_CA_CERTS: path.join(fixture, 'tls-cert.pem'),
        OTEL_NODE_DISABLED_INSTRUMENTATIONS: disableHttpInstrumentation ? 'http' : '',
        TEST_TLS_PORT: String(upstream.address().port), MONITOR_VERSION: 'local-http-proof'},
      windowsHide: true,
    });
    t.after(async () => {
      if (child.exitCode === null) {child.kill(); await once(child, 'exit');}
    });
    let stdout = '', stderr = '';
    child.stdout.on('data', bytes => {stdout += bytes;});
    child.stderr.on('data', bytes => {stderr += bytes;});
    const deadline = Date.now() + 15000;
    while (!stdout.includes('Serving function...')) {
      assert.equal(child.exitCode, null, stderr);
      assert(Date.now() < deadline, stderr);
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    async function invoke(execution, headers = {}) {
      return new Promise((resolve, reject) => {
        http.get({hostname: '127.0.0.1', port, headers: {
          'Synthetic-Execution-Id': execution, baggage: 'private=value', ...headers,
        }}, res => {
          let body = '';
          res.on('data', bytes => {body += bytes;});
          res.on('end', () => resolve(JSON.parse(body)));
        }).on('error', reject);
      });
    }
    // No manually activated span: cover both a new root and a real remote parent.
    for (const [execution, parent] of [['http-root', undefined], ['http-parent',
      '00-' + '1'.repeat(32) + '-' + '2'.repeat(16) + '-01']]) {
      const start = requests.length;
      const result = await invoke(execution, parent ? {traceparent: parent} : {});
      assert.equal(result.synthetic_generic_result_v1.ok, true, JSON.stringify(result) + '\n' + stderr + '\n' + stdout);
      const sent = requests.slice(start);
      assert.deepEqual(sent.map(r => r.path), ['/', '/product/P1', '/cart']);
      const trace = sent[0].headers.traceparent?.split('-')[1];
      assert.match(trace, /^[0-9a-f]{32}$/);
      assert.notEqual(trace, '0'.repeat(32));
      if (parent) assert.equal(trace, '1'.repeat(32));
      assert(sent.every(r => r.headers.traceparent.split('-')[1] === trace));
      assert(sent.every(r => r.headers.baggage === undefined));
      assert(sent.every(r => r.headers.cookie === 'shop_session-id=' + sessionForExecution(execution)));
      const events = stdout.split('\n').flatMap(line => {
        try {return [JSON.parse(line)];} catch {return [];}
      });
      const passed = events.find(e => e.message === 'synthetic.journey.passed' && e.execution_id === execution);
      assert.equal(passed.application_trace_id, trace);
      assert.equal(passed['logging.googleapis.com/trace'], 'projects/local-sdk-proof/traces/' + trace);
      assert.match(passed['logging.googleapis.com/spanId'], /^[0-9a-f]{16}$/);
      const active = events.filter(e => e.test_outbound).slice(-3);
      assert.equal(active.length, 3);
      assert(active.every(e => e.test_outbound.active && e.test_outbound.span.traceId === trace));
      assert(active.every(e => e.test_outbound.context_manager === 'AsyncLocalStorageContextManager'));
    }
    failProduct = true;
    const beforeFailure = requests.length;
    const failed = await invoke('http-failure');
    assert.equal(failed.synthetic_generic_result_v1.ok, false);
    assert.equal(failed.synthetic_generic_result_v1.generic_error.error_message, 'shop_product_failed');
    assert.equal(requests.length - beforeFailure, 2);
    const messages = stdout.split('\n').flatMap(line => {
      try {return [JSON.parse(line)];} catch {return [];}
    });
    const cleanup = messages.find(e => e.message === 'synthetic.cleanup' && e.execution_id === 'http-failure');
    assert.equal(cleanup.redis_writes, 0);
    assert.equal(cleanup.local_session_discarded, true);
    assert(!stdout.includes('shop_session-id='));
  });
}
