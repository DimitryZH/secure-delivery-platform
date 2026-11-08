'use strict';

const {instantiateAutoInstrumentation, runSyntheticHandler} = require('@google-cloud/synthetics-sdk-api');
// This monitor propagates trace context only; it does not accept baggage.
process.env.OTEL_PROPAGATORS = 'tracecontext';
instantiateAutoInstrumentation();

const functions = require('@google-cloud/functions-framework');
const {context, propagation, trace, SpanKind, isSpanContextValid} = require('@opentelemetry/api');
const {runJourney} = require('./journey');

const handler = runSyntheticHandler(async ({logger, executionId}) => {
  const span = trace.getSpan(context.active());
  if (!span?.isRecording() || !isSpanContextValid(span.spanContext())) {
    throw new Error('synthetic_trace_context_missing');
  }
  await runJourney({
    logger,
    executionId,
    traceId: span?.spanContext().traceId,
    monitorVersion: process.env.MONITOR_VERSION,
  });
});

functions.http('SyntheticFunction', (req, res) => {
  // Framework CLI loads HTTP before user code. Do not depend on its server hook.
  const parent = propagation.extract(context.active(), req.headers);
  return trace.getTracer('shop-dev-browse-v1').startActiveSpan(
    'shop.synthetic.browse', {kind: SpanKind.SERVER}, parent, async span => {
      try {
        return await handler(req, res);
      } finally {
        span.end();
      }
    });
});
