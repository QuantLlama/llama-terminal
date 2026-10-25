/**
 * Content of the setup guide, in both languages. Structure follows the language
 * and the copy follows the reader: commands, variable names and repository
 * paths are identical in both, because they are the thing being typed.
 *
 * Loaded as a plain script before SetupGuide.js, so `window.SetupGuideContent`
 * exists on load.
 */
(function (global) {
  var content = {
    es: {
      eyebrow: 'Guía de instalación',
      title: 'Conecta la plataforma con tu máquina',
      subtitle: 'Tu terminal sigue corriendo en tu máquina; la plataforma habla con él por HTTP.',
      indexTitle: 'Contenido',
      sections: {
        overview: 'Resumen',
        env: 'Variables',
        steps: 'Pasos',
        troubleshooting: 'Problemas'
      },
      intro: 'MetaTrader 5 corre sólo en Windows, así que la plataforma no puede llegar sola al bróker. El terminal se queda en tu máquina y un bridge chico (mt5_server.py) lo expone por HTTP: la plataforma alcanza ese bridge y nada más.',
      topology: {
        title: 'Camino del dato',
        nodes: [
          { label: 'Terminal MetaTrader 5', detail: 'tu máquina, cuenta del bróker iniciada' },
          { label: 'Bridge mt5_server.py', detail: 'puerto 8081, X-Bridge-Token obligatorio' },
          { label: 'Red privada', detail: 'Tailscale o WireGuard, nunca pública' },
          { label: 'Contenedor en la nube', detail: 'MT5_BRIDGE_URL apunta acá' }
        ],
        caption: 'Terminal, bridge, red privada, contenedor. No hay nada más expuesto.'
      },
      envTitle: 'Variables de entorno',
      envHeader: { name: 'Variable', value: 'Por defecto', description: 'Qué hace' },
      env: [
        ['MT5_BRIDGE_BIND', '127.0.0.1', 'Interfaz donde escucha el bridge. Pon 0.0.0.0 para exponerlo en la red privada.'],
        ['MT5_BRIDGE_PORT', '8081', 'Puerto donde escucha el bridge. La URL de la plataforma tiene que usar el mismo puerto.'],
        ['MT5_BRIDGE_TOKEN', '(sin definir)', 'Token compartido que se valida en cada pedido. Obligatorio en cuanto otra máquina pueda alcanzar el bridge.'],
        ['MT5_BRIDGE_URL', 'http://127.0.0.1:8081', 'Dónde busca la plataforma el bridge cuando la variable no está definida.']
      ],
      stepsTitle: 'Pasos',
      steps: [
        {
          n: 1,
          title: 'Instala MetaTrader 5 e inicia sesión en tu bróker',
          blocks: [
            { p: 'El paquete Python MetaTrader5 corre sólo en Windows, así que el terminal siempre queda en tu máquina. Instálalo ahí o córrelo en Linux con Wine.' },
            { list: [
              'Inicia sesión en tu cuenta del bróker dentro del terminal. Los datos de mercado y las órdenes necesitan una sesión autenticada.',
              'Deja el terminal abierto: el bridge maneja el terminal que ya está corriendo.'
            ] }
          ]
        },
        {
          n: 2,
          title: 'Prepara el proyecto en la misma máquina',
          blocks: [
            { p: 'Clona el repositorio y deja que el script de instalación arme el entorno e instale requirements.txt.' },
            { code: ['./setup_env.sh                 # Linux and macOS, creates venv_linux', 'setup_env.bat                  # Windows, creates venv'] },
            { note: 'Córrelo desde la raíz del proyecto. Instala la misma lista de dependencias que trae la plataforma.' }
          ]
        },
        {
          n: 3,
          title: 'Genera el token del bridge',
          blocks: [
            { code: ['python -c "import secrets; print(secrets.token_urlsafe(32))"'] },
            { p: 'Copia el valor que imprime. El bridge puede enviar órdenes reales, así que el token es obligatorio en cuanto sea alcanzable desde otra máquina: quien tenga la URL y el token tiene el mismo acceso de trading que tú.' },
            { note: 'Mantén el token fuera de git, de las capturas y de los tickets de soporte. Para rotarlo, cámbialo de los dos lados y reinicia los dos procesos.' }
          ]
        },
        {
          n: 4,
          title: 'Arranca el bridge con ese token',
          blocks: [
            { p: 'Windows, en el entorno donde corre MetaTrader 5:' },
            { code: ['set MT5_BRIDGE_BIND=0.0.0.0', 'set MT5_BRIDGE_TOKEN=<your token>', 'start_mt5_server.bat'] },
            { p: 'Linux con Wine, dentro del mismo prefix:' },
            { code: ['export MT5_BRIDGE_BIND=0.0.0.0', 'export MT5_BRIDGE_TOKEN=<your token>', 'wine python -m uvicorn mt5_server:app --host "$MT5_BRIDGE_BIND" --port 8081'] },
            { note: 'MT5_BRIDGE_PORT usa 8081 por defecto. La combinación 127.0.0.1 sin token es el modo sólo escritorio; no la dejes así cuando otra máquina necesite conectarse.' }
          ]
        },
        {
          n: 5,
          title: 'Conecta los dos lados',
          blocks: [
            { p: 'El proceso de la plataforma necesita dos valores que coincidan exactamente con el bridge:' },
            { list: [
              'MT5_BRIDGE_URL: la dirección que alcanza el bridge desde la máquina donde corre la plataforma.',
              'MT5_BRIDGE_TOKEN: el mismo token con el que arrancaste el bridge.'
            ] },
            { p: 'Si MT5_BRIDGE_URL no está definida, la plataforma cae en http://127.0.0.1:8081, que sólo funciona cuando el bridge y la plataforma comparten host.' },
            { note: 'Mantén el bridge en una red privada como Tailscale, nunca en una dirección pública.' }
          ]
        },
        {
          n: 6,
          title: 'Verifica de punta a punta',
          blocks: [
            { p: 'Primero el bridge, desde la máquina que lo corre:' },
            { code: ['curl -s -H "X-Bridge-Token: <your token>" http://127.0.0.1:8081/api/balance'] },
            { p: 'Después la plataforma. Su respuesta de /api/health tiene que mostrar mt5_status connected y services.market_data ONLINE:' },
            { code: ['{"ready_for_ui": true,', ' "mt5_status": "connected",', ' "services": { "market_data": "ONLINE" } }'] },
            { p: 'En el terminal, la barra de estado del pie nombra la plataforma y muestra CONNECTED cuando el bridge responde.' }
          ]
        },
        {
          n: 7,
          title: 'Agrega cuentas de cripto (opcional)',
          blocks: [
            { p: 'Las claves de exchange CCXT se cargan dentro de la app: abre Ajustes con el engranaje de la barra superior y usa la pestaña Cuentas para agregar una cuenta CRYPTO con su API key, secret y passphrase si el exchange la pide.' },
            { note: 'Algunos exchanges bloquean la región del servidor. Cuando pasa, el despliegue necesita además un proxy de salida; eso es tarea de operación y está en el runbook de la nube.' }
          ]
        }
      ],
      troubleshootingTitle: 'Problemas frecuentes',
      troubleshooting: [
        ['401 token de bridge inválido', 'El token no coincide entre el bridge y la plataforma. Define el mismo MT5_BRIDGE_TOKEN de los dos lados y reinicia ambos.'],
        ['Nada responde en el puerto', 'El bridge no está corriendo, o un firewall descarta 8081. Pon 0.0.0.0 y habilita 8081 sólo en la interfaz privada.'],
        ['Responde local, no desde la nube', 'La red privada está caída. Verifica que las dos máquinas estén conectadas y se vean entre sí.'],
        ['No puede conectar con MT5', 'El terminal está cerrado o sin sesión en la cuenta del bróker. Ábrelo, inicia sesión y reintenta.'],
        ['Puerto equivocado', 'MT5_BRIDGE_PORT y el puerto dentro de MT5_BRIDGE_URL tienen que coincidir. Por defecto es 8081.']
      ],
      sourcesNote: 'El runbook de operación del repositorio y el documento de la nube guardan el mismo procedimiento para soporte.',
      sources: ['deploy/MT5_BRIDGE.md', 'docs/CLOUD.md'],
      securityNote: 'Quien tenga la URL del bridge y el token puede operar en el terminal con sesión iniciada.',
      closeLabel: 'Cerrar',
      languageLabel: 'Idioma'
    },

    en: {
      eyebrow: 'Setup guide',
      title: 'Connect this platform to your machine',
      subtitle: 'Your terminal keeps running locally; the platform talks to it over HTTP.',
      indexTitle: 'Contents',
      sections: {
        overview: 'Overview',
        env: 'Variables',
        steps: 'Steps',
        troubleshooting: 'Troubleshooting'
      },
      intro: 'MetaTrader 5 is Windows-only, so the platform cannot reach a broker on its own. The terminal stays on your machine and a small bridge (mt5_server.py) exposes it over HTTP; the platform reaches that bridge and nothing else.',
      topology: {
        title: 'Data path',
        nodes: [
          { label: 'MetaTrader 5 terminal', detail: 'your machine, broker account logged in' },
          { label: 'mt5_server.py bridge', detail: 'port 8081, X-Bridge-Token required' },
          { label: 'Private network', detail: 'Tailscale or WireGuard, never public' },
          { label: 'Cloud container', detail: 'MT5_BRIDGE_URL points here' }
        ],
        caption: 'Terminal, then bridge, then private network, then container. Nothing else is exposed.'
      },
      envTitle: 'Environment variables',
      envHeader: { name: 'Variable', value: 'Default', description: 'What it does' },
      env: [
        ['MT5_BRIDGE_BIND', '127.0.0.1', 'Interface the bridge listens on. Set 0.0.0.0 to expose it on the private network.'],
        ['MT5_BRIDGE_PORT', '8081', 'Port the bridge listens on. The platform URL must use the same port.'],
        ['MT5_BRIDGE_TOKEN', '(unset)', 'Shared token checked on every request. Required as soon as another machine can reach the bridge.'],
        ['MT5_BRIDGE_URL', 'http://127.0.0.1:8081', 'Where the platform looks for the bridge when the variable is unset.']
      ],
      stepsTitle: 'Steps',
      steps: [
        {
          n: 1,
          title: 'Install MetaTrader 5 and log in to your broker',
          blocks: [
            { p: 'The MetaTrader5 Python package runs on Windows only, so the terminal always stays on your machine. Install it there, or run it on Linux through Wine.' },
            { list: [
              'Log in to your broker account inside the terminal. Market data and orders need an authenticated session.',
              'Leave the terminal open: the bridge drives the terminal that is already running.'
            ] }
          ]
        },
        {
          n: 2,
          title: 'Get the project running on the same machine',
          blocks: [
            { p: 'Clone the repository and let the setup script build the environment and install requirements.txt.' },
            { code: ['./setup_env.sh                 # Linux and macOS, creates venv_linux', 'setup_env.bat                  # Windows, creates venv'] },
            { note: 'Run it from the project root. It installs the same dependency list the platform ships with.' }
          ]
        },
        {
          n: 3,
          title: 'Generate the bridge token',
          blocks: [
            { code: ['python -c "import secrets; print(secrets.token_urlsafe(32))"'] },
            { p: 'Copy the printed value. The bridge can place real orders, so the token is mandatory the moment it is reachable from another machine, and anyone holding the URL and the token has the same trading access you do.' },
            { note: 'Keep the token out of git, screenshots and support tickets. Rotate it by changing it on both sides and restarting both processes.' }
          ]
        },
        {
          n: 4,
          title: 'Start the bridge with that token',
          blocks: [
            { p: 'Windows, in the environment where MetaTrader 5 runs:' },
            { code: ['set MT5_BRIDGE_BIND=0.0.0.0', 'set MT5_BRIDGE_TOKEN=<your token>', 'start_mt5_server.bat'] },
            { p: 'Linux with Wine, inside the same prefix:' },
            { code: ['export MT5_BRIDGE_BIND=0.0.0.0', 'export MT5_BRIDGE_TOKEN=<your token>', 'wine python -m uvicorn mt5_server:app --host "$MT5_BRIDGE_BIND" --port 8081'] },
            { note: 'MT5_BRIDGE_PORT defaults to 8081. The pair 127.0.0.1 with no token is the desktop-only default; never keep it once another machine needs to connect.' }
          ]
        },
        {
          n: 5,
          title: 'Connect the two sides',
          blocks: [
            { p: 'The platform process needs two values that match the bridge exactly:' },
            { list: [
              'MT5_BRIDGE_URL: the address that reaches the bridge from the machine running the platform.',
              'MT5_BRIDGE_TOKEN: the same token the bridge was started with.'
            ] },
            { p: 'When MT5_BRIDGE_URL is unset the platform falls back to http://127.0.0.1:8081, which only works when the bridge and the platform share a host.' },
            { note: 'Keep the bridge on a private network such as Tailscale, not on a public address.' }
          ]
        },
        {
          n: 6,
          title: 'Verify end to end',
          blocks: [
            { p: 'First the bridge itself, from the machine that runs it:' },
            { code: ['curl -s -H "X-Bridge-Token: <your token>" http://127.0.0.1:8081/api/balance'] },
            { p: 'Then the platform. Its /api/health response must show mt5_status connected and services.market_data ONLINE:' },
            { code: ['{"ready_for_ui": true,', ' "mt5_status": "connected",', ' "services": { "market_data": "ONLINE" } }'] },
            { p: 'In the terminal, the status bar along the bottom of the screen names the platform and shows CONNECTED once the bridge answers.' }
          ]
        },
        {
          n: 7,
          title: 'Add crypto accounts (optional)',
          blocks: [
            { p: 'CCXT exchange keys are entered inside the app: open Settings from the gear button in the top bar and use the Accounts tab to add a CRYPTO account with its API key, secret and passphrase if the venue asks for one.' },
            { note: 'Some venues block the server region. When that happens the deployment also needs an egress proxy; that is an operator concern documented in the cloud runbook.' }
          ]
        }
      ],
      troubleshootingTitle: 'Troubleshooting',
      troubleshooting: [
        ['401 invalid bridge token', 'The token differs between the bridge and the platform. Set the same MT5_BRIDGE_TOKEN on both sides and restart both.'],
        ['Nothing answers on the port', 'The bridge is not running, or a firewall drops 8081. Bind 0.0.0.0 and allow 8081 only on the private interface.'],
        ['Reachable locally, not from the cloud', 'The private network is down. Check that both machines are signed in and can see each other.'],
        ['Could not connect to MT5', 'The terminal is closed or not logged in to the broker account. Open it, sign in, and retry.'],
        ['Wrong port', 'MT5_BRIDGE_PORT and the port inside MT5_BRIDGE_URL must agree. The default is 8081.']
      ],
      sourcesNote: 'The operator runbook in the repository and the cloud document hold the same procedure for support.',
      sources: ['deploy/MT5_BRIDGE.md', 'docs/CLOUD.md'],
      securityNote: 'Anyone holding the bridge URL and token can trade on the signed-in terminal.',
      closeLabel: 'Close',
      languageLabel: 'Language'
    }
  };

  global.SetupGuideContent = content;
})(typeof window !== 'undefined' ? window : globalThis);
