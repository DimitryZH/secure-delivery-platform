'use strict';

const https = require('node:https');
const {createHash} = require('node:crypto');

const ORIGIN = 'https://shop.runtimeplatforms.dev';
const MAX_BYTES = 2 * 1024 * 1024;

function sessionForExecution(executionId) {
  if (typeof executionId !== 'string' || !executionId || executionId.length > 256) {
    throw new Error('synthetic_execution_id_missing');
  }
  return 'issue115-' + createHash('sha256').update(executionId).digest('hex').slice(0, 32);
}

function getHtml(path, headers, timeout) {
  const {context, propagation} = require('@opentelemetry/api');
  // Propagate even when the framework loaded HTTPS before auto-instrumentation.
  const outboundHeaders = {...headers};
  propagation.inject(context.active(), outboundHeaders);
  return new Promise((resolve, reject) => {
    const request = https.request(new URL(path, ORIGIN), {
      method: 'GET',
      headers: outboundHeaders,
      rejectUnauthorized: true,
    }, response => {
      let length = 0;
      const chunks = [];
      response.on('data', chunk => {
        length += chunk.length;
        if (length > MAX_BYTES) {
          request.destroy(new Error('response_too_large'));
          return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => resolve({
        status: response.statusCode,
        body: Buffer.concat(chunks).toString('utf8'),
      }));
      response.on('error', reject);
    });
    // An absolute timer bounds DNS, connection, TLS and body reads together.
    const timer = setTimeout(() => request.destroy(new Error('request_timeout')), timeout);
    request.on('close', () => clearTimeout(timer));
    request.on('error', reject);
    request.end();
  });
}

async function runJourney({logger, executionId, traceId, monitorVersion, get = getHtml, now = Date.now}) {
  if (!/^[0-9a-f]{32}$/.test(traceId || '')) {
    throw new Error('synthetic_trace_context_missing');
  }
  const started = now();
  const deadline = started + 30000;
  const attribution = {
    monitor: 'shop-dev-browse-v1',
    monitor_version: monitorVersion,
    environment: 'dev',
    application_trace_id: traceId,
    execution_id: executionId,
  };
  let cookie = 'shop_session-id=' + sessionForExecution(executionId);
  let requests = 0;
  let step = 'catalog';
  async function page(path) {
    if (++requests > 3) throw new Error('request_budget_exceeded');
    const remaining = deadline - now();
    if (remaining <= 0) throw new Error('journey_deadline_exceeded');
    const response = await get(path, {
      Cookie: cookie,
      'User-Agent': 'sdp-online-shop-synthetic/browse-v1',
      'X-SDP-Synthetic': 'browse-v1',
    }, Math.min(8000, remaining));
    if (now() > deadline) throw new Error('journey_deadline_exceeded');
    if (response.status !== 200) throw new Error('unexpected_http_status');
    return response.body;
  }
  try {
    const home = await page('/');
    const product = /href="\/product\/([A-Za-z0-9_-]+)"/.exec(home);
    if (!product) throw new Error('catalog_product_link_missing');
    step = 'product';
    const detail = await page('/product/' + product[1]);
    if (!detail.includes(product[1])) throw new Error('product_identity_missing');
    step = 'cart';
    const cart = await page('/cart');
    if (!cart.includes('Your shopping cart is empty!')) throw new Error('isolated_cart_not_empty');
    logger.info('synthetic.journey.passed', {...attribution, requests, duration_ms: now() - started});
  } catch (error) {
    logger.error('synthetic.journey.failed', {...attribution, step, requests});
    // SDK stores this bounded message. Headers, session and response bodies stay private.
    throw new Error('shop_' + step + '_failed', {cause: error});
  } finally {
    cookie = '';
    logger.info('synthetic.cleanup', {...attribution, redis_writes: 0, local_session_discarded: true});
  }
}

module.exports = {runJourney, sessionForExecution};
