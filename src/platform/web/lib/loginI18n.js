/**
 * Minimal login i18n: two dictionaries, a stored preference and a browser
 * fallback. No dependency, no build step: the page loads this file as a plain
 * script before the component, so `window.LoginI18n` must exist on load.
 *
 * Scope is the login and its help. The rest of the platform keeps its copy.
 */
(function (global) {
  var STORAGE_KEY = 'ql_lang';
  var LANGUAGES = ['es', 'en'];
  var DEFAULT_LANGUAGE = 'en';

  var dictionaries = {
    es: {
      'brand.tagline': 'Terminal Profesional',
      'dialog.label': 'Acceso a Quantum Llama Professional',

      'form.title': 'Iniciar sesión',
      'form.section': 'Acceso',
      'form.subtitle': 'Usa el email asociado a tu suscripción.',
      'session.state': 'Sin sesión',

      'label.email': 'Email',
      'label.password': 'Contraseña',
      'label.remember': 'Recordar credenciales',

      'action.signIn': 'Iniciar sesión',
      'action.signingIn': 'Ingresando',
      'action.showPassword': 'Mostrar contraseña',
      'action.hidePassword': 'Ocultar contraseña',

      'error.invalidCredentials': 'Credenciales inválidas.',
      'error.subscriptionRequired': 'Acceso restringido: se requiere una cuenta PREMIUM.',
      'error.unknown': 'No se pudo iniciar sesión. Inténtalo de nuevo.',

      'update.available': 'Actualización disponible',
      'update.restart': 'Reinicia la plataforma para aplicarla.',

      'help.toggle': 'Ayuda de configuración',
      'help.title': 'Qué necesitas para operar',
      'help.intro': 'Quantum Llama lee el mercado desde tu MetaTrader 5 y reúne flujo de órdenes, footprint, DOM y perfil de volumen en una sola pantalla.',
      'help.requirements.title': 'Requisitos',
      'help.requirements.1': 'MetaTrader 5 instalado y con la cuenta del bróker iniciada.',
      'help.requirements.2': 'El proyecto instalado en la misma máquina que MT5.',
      'help.requirements.3': 'Red privada entre tu máquina y el contenedor: Tailscale o WireGuard.',
      'help.steps.title': 'Primeros pasos',
      'help.steps.1': 'Genera el token del bridge y guárdalo.',
      'help.steps.2': 'Arranca el bridge con ese token en el puerto 8081.',
      'help.steps.3': 'Apunta MT5_BRIDGE_URL al bridge y comprueba /health.',
      'help.bridge.title': 'El bridge',
      'help.bridge': 'El bridge es el único proceso que habla con MT5. La nube nunca abre el puerto al público: cada pedido viaja firmado con el token.',
      'help.guide': 'Guía completa',
      'help.plans': 'Planes PREMIUM',
      'help.close': 'Cerrar',

      'footer.stack': 'Bridge privado',

      'lang.label': 'Idioma',
      'boot.loading': 'Cargando Quantum Llama...'
    },

    en: {
      'brand.tagline': 'Professional Terminal',
      'dialog.label': 'Sign in to Quantum Llama Professional',

      'form.title': 'Sign in',
      'form.section': 'Access',
      'form.subtitle': 'Use the email address tied to your subscription.',
      'session.state': 'Signed out',

      'label.email': 'Email',
      'label.password': 'Password',
      'label.remember': 'Remember credentials',

      'action.signIn': 'Sign in',
      'action.signingIn': 'Signing in',
      'action.showPassword': 'Show password',
      'action.hidePassword': 'Hide password',

      'error.invalidCredentials': 'Invalid credentials.',
      'error.subscriptionRequired': 'Restricted access: PREMIUM account required.',
      'error.unknown': 'Sign-in failed. Try again.',

      'update.available': 'Update available',
      'update.restart': 'Restart the platform to apply it.',

      'help.toggle': 'Setup help',
      'help.title': 'What you need to trade',
      'help.intro': 'Quantum Llama reads the market from your MetaTrader 5 and puts order flow, footprint, DOM and volume profile on one screen.',
      'help.requirements.title': 'Requirements',
      'help.requirements.1': 'MetaTrader 5 installed and logged in to your broker account.',
      'help.requirements.2': 'The project installed on the same machine as MT5.',
      'help.requirements.3': 'A private network between your machine and the container: Tailscale or WireGuard.',
      'help.steps.title': 'First steps',
      'help.steps.1': 'Generate the bridge token and keep it.',
      'help.steps.2': 'Start the bridge with that token on port 8081.',
      'help.steps.3': 'Point MT5_BRIDGE_URL at the bridge and check /health.',
      'help.bridge.title': 'The bridge',
      'help.bridge': 'The bridge is the only process that talks to MT5. The cloud never opens the port to the public: every request travels signed with the token.',
      'help.guide': 'Full guide',
      'help.plans': 'PREMIUM plans',
      'help.close': 'Close',

      'footer.stack': 'Private bridge',

      'lang.label': 'Language',
      'boot.loading': 'Loading Quantum Llama...'
    }
  };

  function isSupported(language) {
    return LANGUAGES.indexOf(language) !== -1;
  }

  function detectLanguage(language) {
    if (typeof language !== 'string') return DEFAULT_LANGUAGE;
    var primary = language.trim().toLowerCase().split(/[-_]/)[0];
    return primary === 'es' ? 'es' : DEFAULT_LANGUAGE;
  }

  function readStored() {
    try {
      return global.localStorage ? global.localStorage.getItem(STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function getLanguage() {
    var stored = readStored();
    if (isSupported(stored)) return stored;
    var navigatorLanguage = global.navigator ? global.navigator.language : null;
    return detectLanguage(navigatorLanguage);
  }

  function tIn(language, key) {
    var current = dictionaries[language];
    if (current && typeof current[key] === 'string') return current[key];
    var fallback = dictionaries[DEFAULT_LANGUAGE];
    if (fallback && typeof fallback[key] === 'string') return fallback[key];
    return null;
  }

  function lookup(key) {
    return tIn(getLanguage(), key);
  }

  function t(key) {
    var value = lookup(key);
    return value === null ? key : value;
  }

  function has(key) {
    return lookup(key) !== null;
  }

  function applyStatic(root) {
    var scope = root || (global.document ? global.document : null);
    if (!scope || typeof scope.querySelectorAll !== 'function') return;
    var nodes = scope.querySelectorAll('[data-login-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute('data-login-i18n');
      if (!has(key)) continue;
      nodes[i].textContent = t(key);
    }
  }

  function setLanguage(language) {
    if (!isSupported(language)) {
      throw new TypeError('Unsupported language: ' + language);
    }
    try {
      global.localStorage.setItem(STORAGE_KEY, language);
    } catch (err) {
      /* Private mode: the choice just does not survive a reload. */
    }
    applyStatic();
    return language;
  }

  global.LoginI18n = {
    STORAGE_KEY: STORAGE_KEY,
    LANGUAGES: LANGUAGES,
    dictionaries: dictionaries,
    detectLanguage: detectLanguage,
    getLanguage: getLanguage,
    setLanguage: setLanguage,
    has: has,
    t: t,
    tIn: tIn,
    applyStatic: applyStatic
  };
})(typeof window !== 'undefined' ? window : globalThis);
