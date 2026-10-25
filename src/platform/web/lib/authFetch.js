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

  // Routes that must stay anonymous: crawling, readiness and version probes.
  const PUBLIC_PREFIXES = ['/api/readiness', '/api/platform/version'];

  function needsAuthorization(input) {
    let url;
    try {
      url = typeof input === 'string' ? input : (input && input.url) || '';
    } catch (error) {
      return false;
    }
    if (typeof url !== 'string' || url.indexOf('/api/') === -1) return false;
    // Only same-origin API traffic; absolute URLs to other hosts keep their own rules.
    if (/^[a-z]+:\/\//i.test(url)) {
      try {
        if (new URL(url).origin !== global.location.origin) return false;
      } catch (error) {
        return false;
      }
    }
    return !PUBLIC_PREFIXES.some(function (prefix) { return url.indexOf(prefix) === 0; });
  }

  /*
   * Install the helper as the page default.
   *
   * Requiring every call site to opt in was wrong three times in a row: a route
   * became protected, one fetch kept the bare form, and the screen died on a 401
   * body that was not the array the renderer expected. Wrapping the global fetch
   * makes authentication the default and an omission impossible.
   */
  function installDefaultFetch() {
    if (typeof global.fetch !== 'function' || global.fetch.__qlAuthWrapped) return;

    const original = global.fetch;

    async function wrappedFetch(input, init) {
      if (!needsAuthorization(input)) return original(input, init);
      const options = Object.assign({}, init || {});
      const token = await currentAccessToken();
      if (token) {
        options.headers = withAuthorizationHeader(options.headers, token);
      }
      return original(input, options);
    }

    wrappedFetch.__qlAuthWrapped = true;
    global.fetch = wrappedFetch;
  }

  global.authFetch = authFetch;

  if (typeof global.fetch === 'function') {
    installDefaultFetch();
  } else if (typeof global.addEventListener === 'function') {
    // Defensive: only needed if the script somehow loads before fetch exists.
    global.addEventListener('load', installDefaultFetch, { once: true });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { authFetch: authFetch, needsAuthorization: needsAuthorization };
  }
})(typeof window !== 'undefined' ? window : globalThis);
