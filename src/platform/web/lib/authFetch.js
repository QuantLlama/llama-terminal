/*
 * authFetch — the only sanctioned way for the browser to call per-user API routes.
 *
 * Per-user handlers (/api/config, /api/workspace/*, /api/workspaces,
 * /api/algolab/state, /api/algolab/chat*) derive the tenant from a Supabase
 * bearer token and answer 401 without one. This helper reads the current
 * session from the client index.html already created (window.supabase) and adds
 *
 *     Authorization: Bearer <access_token>
 *
 * When there is no session — no client, a null session, or a failing
 * getSession() — the request is still performed, just without the header, so the
 * API answers 401 and logged-out flows degrade predictably instead of throwing
 * inside render code.
 *
 * The token is read from the session on every call. It is never logged, never
 * persisted and never placed in a URL.
 */
(function (global) {
  'use strict';

  const BEARER_PREFIX = 'Bearer ';

  function withAuthorizationHeader(headers, token) {
    const value = BEARER_PREFIX + token;

    if (typeof Headers !== 'undefined' && headers instanceof Headers) {
      const next = new Headers(headers);
      if (!next.has('Authorization')) next.set('Authorization', value);
      return next;
    }

    if (Array.isArray(headers)) {
      const present = headers.some(function (pair) {
        return String(pair[0]).toLowerCase() === 'authorization';
      });
      const pairs = headers.slice();
      if (!present) pairs.push(['Authorization', value]);
      return pairs;
    }

    const next = Object.assign({}, headers || {});
    const present = Object.keys(next).some(function (name) {
      return name.toLowerCase() === 'authorization';
    });
    if (!present) next.Authorization = value;
    return next;
  }

  async function currentAccessToken() {
    try {
      const client = global.supabase;
      if (!client || !client.auth || typeof client.auth.getSession !== 'function') {
        return null;
      }
      const result = await client.auth.getSession();
      const session = result && result.data ? result.data.session : null;
      const token = session && session.access_token;
      if (typeof token === 'string' && token.length > 0) return token;
      return null;
    } catch (error) {
      // No usable session: fall through to an unauthenticated request.
      return null;
    }
  }

  async function authFetch(input, init) {
    const options = Object.assign({}, init || {});
    const token = await currentAccessToken();
    if (token) {
      options.headers = withAuthorizationHeader(options.headers, token);
    }
    return global.fetch(input, options);
  }

  global.authFetch = authFetch;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { authFetch: authFetch };
  }
})(typeof window !== 'undefined' ? window : globalThis);
