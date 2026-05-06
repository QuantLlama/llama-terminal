const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

/**
 * Cross-platform script to run python from the venv
 * Usage: node scripts/run-venv.js <script_path> [args...]
 */

const isWin = process.platform === 'win32';
const venvFolder = isWin ? 'Scripts' : 'bin';
const pythonExe = isWin ? 'python.exe' : 'python';

const rootDir = path.join(__dirname, '..');
const venvPath = path.join(rootDir, 'venv');
const pythonPath = path.join(venvPath, venvFolder, pythonExe);
const pyvenvCfgPath = path.join(venvPath, 'pyvenv.cfg');

// --- Reparar venv si fue movido ---
if (fs.existsSync(pyvenvCfgPath)) {
  try {
    let systemPython = '';
    if (isWin) {
      try {
        systemPython = execSync('where python').toString().split('\r\n')[0].trim();
      } catch (e) {
        systemPython = 'python.exe';
      }
    } else {
      try {
        systemPython = execSync('which python3 || which python').toString().trim();
      } catch (e) {
        systemPython = 'python3';
      }
    }
    const systemPyDir = path.dirname(systemPython);
    
    if (systemPyDir && systemPyDir !== '.') {
      let content = fs.readFileSync(pyvenvCfgPath, 'utf8');
      const lines = content.split(/\r?\n/);
      let changed = false;
      const newLines = lines.map(line => {
        if (line.startsWith('home =')) {
          const oldPath = line.split('=')[1].trim();
          if (oldPath.toLowerCase() !== systemPyDir.toLowerCase()) {
            changed = true;
            return `home = ${systemPyDir}`;
          }
        }
        return line;
      });

      if (changed) {
        fs.writeFileSync(pyvenvCfgPath, newLines.join('\n'));
        console.log('🔧 Entorno virtual auto-reparado para este sistema.');
      }
    }
  } catch (err) {
    console.warn('Advertencia: No se pudo reparar pyvenv.cfg automáticamente:', err.message);
  }
}

if (!fs.existsSync(pythonPath)) {
  console.error(`Error: Python no encontrado en ${pythonPath}`);
  console.error(`Asegúrate de que el entorno virtual esté creado en la carpeta 'venv'.`);
  process.exit(1);
}

const args = process.argv.slice(2);
const pythonProcess = spawn(pythonPath, args, {
  stdio: 'inherit',
  env: process.env
});

pythonProcess.on('exit', (code) => {
  process.exit(code);
});

pythonProcess.on('error', (err) => {
  console.error('Error al iniciar el proceso de python:', err);
  process.exit(1);
});
