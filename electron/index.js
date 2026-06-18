const bytenode = require('bytenode');
const { app } = require('electron');
const path = require('path');
const fs = require('fs');

if (app.isPackaged) {
  // In production, load the compiled bytecode from the same directory
  const jscPath = path.join(__dirname, 'main.jsc');
  if (fs.existsSync(jscPath)) {
    try {
      require('v8').setFlagsFromString('--no-lazy');
      require(jscPath);
    } catch (e) {
      console.error('Failed to load main.jsc, falling back to source', e);
      require('./main.js');
    }
  } else {
    // Fallback in case of emergency (though if it fails here, something is wrong)
    require('./main.js');
  }
} else {
  // In development, load the original source
  require('./main.js');
}
