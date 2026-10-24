// Compile into a fresh build tree, never beside source or stale bytecode.
const bytenode = require('bytenode');
const fs = require('fs');
const path = require('path');
const ROOT = path.dirname(__dirname);
const ELECTRON_DIR = path.join(ROOT, 'electron');
const DIST_DIR = path.join(ROOT, 'build', 'electron');

async function compile() {
  const build = path.join(ROOT, 'build');
  if (fs.existsSync(build) && fs.lstatSync(build).isSymbolicLink()) {
    throw new Error('Symlink build directory is not allowed');
  }
  if (fs.existsSync(DIST_DIR) || fs.lstatSync(build, { throwIfNoEntry: false })?.isSymbolicLink()) {
    throw new Error('build/electron must be a fresh output directory');
  }
  const files = ['index.js', 'main.js', 'preload.js', 'preload-loader.js',
    'health.js', 'splash.html', 'trial-expired.html'];
  for (const file of files) {
    if (!fs.lstatSync(path.join(ELECTRON_DIR, file)).isFile()) {
      throw new Error(`Expected regular Electron input: ${file}`);
    }
  }
  if (fs.lstatSync(ELECTRON_DIR).isSymbolicLink()) {
    throw new Error('Symlink Electron source directory is not allowed');
  }
  fs.mkdirSync(DIST_DIR, { recursive: true });
  for (const file of files) {
    fs.copyFileSync(path.join(ELECTRON_DIR, file), path.join(DIST_DIR, file));
  }
  for (const file of ['main.js', 'preload.js']) {
    await bytenode.compileFile({
      filename: path.join(DIST_DIR, file),
      output: path.join(DIST_DIR, file + 'c'),
      compileAsModule: true
    });
    console.log(`[OK] Created build/electron/${file}c`);
  }
}
compile().then(() => process.exit(0)).catch(err => {
  console.error(`[ERROR] ${err.message}`);
  process.exit(1);
});
