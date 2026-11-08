'use strict';

// Test-only transport: real TLS on loopback; never contact Cloud APIs or Shop.
const https = require('node:https');
const {urlToHttpOptions} = require('node:url');
const request = https.request;
https.request = function(url, options, callback) {
  const opts = url instanceof URL ? {...urlToHttpOptions(url), ...options} : {...url};
  const done = typeof options === 'function' ? options : callback;
  if (opts.hostname !== 'shop.runtimeplatforms.dev') throw new Error('unexpected_test_destination');
  const {context, trace} = require('@opentelemetry/api');
  const span = trace.getSpan(context.active());
  console.log(JSON.stringify({test_outbound: {
    path: opts.path,
    active: !!span?.isRecording(),
    span: span?.spanContext(),
    context_manager: context._getContextManager?.().constructor.name,
  }}));
  const outgoing = request.call(this, {...opts,
    port: Number(process.env.TEST_TLS_PORT),
    lookup: (_host, options, done) => options.all ?
      done(null, [{address: '127.0.0.1', family: 4}]) : done(null, '127.0.0.1', 4),
  }, done);
  outgoing.on('error', error => console.error('test_tls_error', error.message));
  return outgoing;
};
const {TraceExporter} = require('@google-cloud/opentelemetry-cloud-trace-exporter');
// Keep the actual provider/context/instrumentation; replace remote export only.
TraceExporter.prototype.export = (spans, done) => done({code: 0});
