const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

let html = fs.readFileSync('frontend/dist/index.html', 'utf8');
html = html.replace('src="/assets/', 'src="assets/').replace('href="/assets/', 'href="assets/');
fs.writeFileSync('frontend/dist/index_local.html', html);

const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const profile = 'D:\\Prep_AI\\chrome-temp-file';
const outPng = 'D:\\Prep_AI\\screenshots\\test_file_landing.png';

const args = [
  `"${chrome}"`,
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-web-security',
  '--allow-file-access-from-files',
  '--enable-logging=stderr',
  '--v=1',
  '--virtual-time-budget=5000',
  `--user-data-dir="${profile}"`,
  '--window-size=1440,900',
  `--screenshot="${outPng}"`,
  '"file:///D:/Prep_AI/frontend/dist/index_local.html"'
].join(' ');

try {
  const res = execSync(args, { encoding: 'utf8' });
  console.log('Result:', res);
  const exists = fs.existsSync(outPng);
  console.log('File created:', exists, exists ? fs.statSync(outPng).size : 0);
} catch (e) {
  console.error('Error:', e.message);
} finally {
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  try { fs.unlinkSync('frontend/dist/index_local.html'); } catch (e) {}
}
