const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

async function test() {
  const wsUrl = 'http://127.0.0.1:9222/json/new?about:blank';
  // Check if Chrome is already on 9222 or spawn it
  let chromeProcess = null;
  let targetWs = null;

  try {
    const res = await fetch(wsUrl, { method: 'PUT' });
    const data = await res.json();
    targetWs = data.webSocketDebuggerUrl;
  } catch (e) {
    chromeProcess = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--remote-debugging-port=9222',
      '--user-data-dir=D:\\Prep_AI\\chrome-debug-profile',
      '--window-size=1440,900'
    ]);
    for (let i = 0; i < 20; i++) {
      try {
        const res = await fetch(wsUrl, { method: 'PUT' });
        const data = await res.json();
        targetWs = data.webSocketDebuggerUrl;
        break;
      } catch (e) { await new Promise(r => setTimeout(r, 200)); }
    }
  }

  const ws = new WebSocket(targetWs);
  await new Promise(r => ws.onopen = r);

  let msgId = 1;
  const send = (method, params = {}) => new Promise(r => {
    const id = msgId++;
    const handler = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id === id) {
        ws.removeEventListener('message', handler);
        r(msg);
      }
    };
    ws.addEventListener('message', handler);
    ws.send(JSON.stringify({ id, method, params }));
  });

  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Runtime.consoleAPICalled') {
      console.log('BROWSER CONSOLE:', msg.params.type, msg.params.args.map(a => a.value || a.description).join(' '));
    }
  });

  await send('Page.enable');
  await send('Runtime.enable');

  console.log('Navigating to /admin...');
  await send('Page.navigate', { url: 'http://localhost:5173/admin?mock_auth=admin' });
  await new Promise(r => setTimeout(r, 3000));

  const evalUrl = await send('Runtime.evaluate', { expression: 'window.location.href' });
  console.log('Current URL:', evalUrl.result.value);

  ws.close();
  if (chromeProcess) chromeProcess.kill();
  process.exit(0);
}

test();

