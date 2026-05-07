const bytenode = require('bytenode');
const { app } = require('electron');
const path = require('path');
const fs = require('fs');

if (app.isPackaged) {
  // In production, load the compiled bytecode from the same directory
  const jscPath = path.join(__dirname, 'main.jsc');
  if (fs.existsSync(jscPath)) {
    require(jscPath);
  } else {
    // Fallback in case of emergency (though if it fails here, something is wrong)
    require('./main.js');
  }
} else {
  // In development, load the original source
  require('./main.js');
}
