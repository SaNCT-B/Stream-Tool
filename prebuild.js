const fs = require('fs');
const path = require('path');

const protoSource = path.join(__dirname, 'node_modules/tiktok-live-connector/dist/proto');
const protoDest = path.join(__dirname, 'dist/proto');

if (!fs.existsSync(protoDest)) {
  fs.mkdirSync(protoDest, { recursive: true });
}

// Copy all .proto files
fs.readdirSync(protoSource).forEach(file => {
  if (file.endsWith('.proto')) {
    fs.copyFileSync(path.join(protoSource, file), path.join(protoDest, file));
  }
});

console.log('Proto files copied to dist/proto');
