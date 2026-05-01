require('bytenode');
const path = require('path');
const fs = require('fs');

// In production, load from the same directory inside the asar
const jscPath = path.join(__dirname, 'preload.jsc');

if (fs.existsSync(jscPath)) {
  require(jscPath);
} else {
  // Fallback for development if this loader is somehow called
  require('./preload.js');
}
