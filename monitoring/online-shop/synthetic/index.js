'use strict';

const {instantiateAutoInstrumentation, runSyntheticHandler} = require('@google-cloud/synthetics-sdk-api');
// This monitor propagates trace context only; it does not accept baggage.
process.env.OTEL_PROPAGATORS = 'tracecontext';
instantiateAutoInstrumentation();

const functions = require('@google-cloud/functions-framework');
const {context, trace} = require('@opentelemetry/api');
const {runJourney} = require('./journey');

functions.http('SyntheticFunction', runSyntheticHandler(async ({logger, executionId}) => {
  const span = trace.getSpan(context.active());
  await runJourney({
    logger,
    executionId,
    traceId: span?.spanContext().traceId,
    monitorVersion: process.env.MONITOR_VERSION,
  });
}));
