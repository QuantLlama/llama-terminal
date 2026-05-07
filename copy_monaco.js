const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'node_modules', 'monaco-editor', 'min', 'vs');
const destDir = path.join(__dirname, 'src', 'platform', 'web', 'lib', 'monaco', 'vs');

function copyDir(src, dest) {
    if (!fs.existsSync(dest)) {
        fs.mkdirSync(dest, { recursive: true });
    }

    const entries = fs.readdirSync(src, { withFileTypes: true });

    for (let entry of entries) {
        const srcPath = path.join(src, entry.name);
        const destPath = path.join(dest, entry.name);

        if (entry.isDirectory()) {
            copyDir(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

console.log(`Copying Monaco Editor from ${srcDir} to ${destDir}...`);
try {
    copyDir(srcDir, destDir);
    console.log('Monaco Editor copied successfully.');
} catch (err) {
    console.error('Error copying Monaco Editor:', err);
}
