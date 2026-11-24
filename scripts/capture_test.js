const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const distDir = path.resolve(__dirname, '..', 'frontend', 'dist');

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf'
};

const server = http.createServer((req, res) => {
  let reqPath = req.url.split('?')[0];
  let filePath = path.join(distDir, reqPath);
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(distDir, 'index.html');
  }
  const ext = path.extname(filePath).toLowerCase();
  const contentType = mimeTypes[ext] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': contentType });
  res.end(fs.readFileSync(filePath));
});

server.listen(5173, '127.0.0.1', () => {
  console.log('Static server started on port 5173');
  try {
    const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
    const profile = 'D:\\Prep_AI\\chrome-temp-test';
    const outPng = 'D:\\Prep_AI\\screenshots\\test_landing.png';
    const args = [
      `"${chrome}"`,
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--virtual-time-budget=4000',
      `--user-data-dir="${profile}"`,
      '--window-size=1440,900',
      `--screenshot="${outPng}"`,
      'http://127.0.0.1:5173/'
    ].join(' ');

    const out = execSync(args, { encoding: 'utf-8' });
    console.log('Capture output:', out);
  } catch (err) {
    console.error('Execution error:', err.message);
  } finally {
    server.close();
    try {
      fs.rmSync('D:\\Prep_AI\\chrome-temp-test', { recursive: true, force: true });
    } catch(e) {}
  }
});
