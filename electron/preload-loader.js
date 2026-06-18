require('bytenode');
const path = require('path');
const fs = require('fs');

// In production, load from the same directory inside the asar
const jscPath = path.join(__dirname, 'preload.jsc');

if (fs.existsSync(jscPath)) {
  try {
    require('v8').setFlagsFromString('--no-lazy');
    require(jscPath);
  } catch (e) {
    console.error('Failed to load preload.jsc, falling back to source', e);
    require('./preload.js');
  }
} else {
  // Fallback for development if this loader is somehow called
  require('./preload.js');
}
