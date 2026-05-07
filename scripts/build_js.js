const bytenode = require('bytenode');
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const ELECTRON_DIR = path.join(ROOT, 'electron');
const DIST_DIR = ELECTRON_DIR;

if (!fs.existsSync(DIST_DIR)) {
  fs.mkdirSync(DIST_DIR, { recursive: true });
}

async function compile() {
  const files = ['main.js', 'preload.js'];
  
  for (const file of files) {
    const srcPath = path.join(ELECTRON_DIR, file);
    const destPath = path.join(DIST_DIR, file + 'c'); // .js -> .jsc
    
    console.log(`Compiling ${file}...`);
    try {
      await bytenode.compileFile({
        filename: srcPath,
        output: destPath,
        compileAsModule: true
      });
      console.log(`[OK] Created ${destPath}`);
    } catch (err) {
      console.error(`[ERROR] Failed to compile ${file}:`, err);
      process.exit(1);
    }
  }
  process.exit(0);
}

compile();
