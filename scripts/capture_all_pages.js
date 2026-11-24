const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const distDir = path.resolve(__dirname, '..', 'frontend', 'dist');
const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

// ── 1. Mock API Server on Port 5000 ─────────────────────────────
const apiServer = http.createServer((req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    return res.end();
  }

  const url = req.url.split('?')[0];

  // Helper response
  const json = (data, code = 200) => {
    res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
  };

  if (url === '/api/health') {
    return json({ status: 'production-ready', ai: 'active' });
  }

  if (url === '/api/auth/login' || url === '/api/auth/google') {
    return json({
      token: 'mock-jwt-token-2026',
      user: {
        id: 'u1',
        name: 'Alex Johnson',
        email: 'alex.johnson@prepai.dev',
        role: 'admin'
      }
    });
  }

  if (url === '/api/auth/verify-email') {
    return json({ success: true, message: 'Email verified successfully.' });
  }

  if (url === '/api/interview/history') {
    return json([
      {
        id: 'sess_1',
        _id: 'sess_1',
        role: 'Senior Full-Stack Engineer',
        target_role: 'Senior Full-Stack Engineer',
        created_at: '2026-11-05T14:30:00Z',
        overall_score: 88,
        technical_score: 90,
        delivery_score: 85,
        questions_count: 5
      },
      {
        id: 'sess_2',
        _id: 'sess_2',
        role: 'Backend Architect (Distributed Systems)',
        target_role: 'Backend Architect (Distributed Systems)',
        created_at: '2026-11-01T09:45:00Z',
        overall_score: 82,
        technical_score: 84,
        delivery_score: 80,
        questions_count: 5
      },
      {
        id: 'sess_3',
        _id: 'sess_3',
        role: 'AI / Machine Learning Engineer',
        target_role: 'AI / Machine Learning Engineer',
        created_at: '2026-10-24T16:20:00Z',
        overall_score: 91,
        technical_score: 94,
        delivery_score: 88,
        questions_count: 5
      }
    ]);
  }

  if (url === '/api/profile/resume/get') {
    return json({
      resume_filename: 'Alex_Johnson_Staff_Engineer_Resume.pdf',
      resume_text: 'Alex Johnson\nSenior Full-Stack Software Engineer with 5+ years of experience building scalable distributed web architectures, high-performance APIs, and AI-assisted workflows.\nTech Stack: React, TypeScript, Node.js, Python, FastAPI, PostgreSQL, Redis, Docker, AWS.',
      ats_score: 88
    });
  }

  if (url === '/api/coding/challenges') {
    return json([
      {
        id: 'dsa_1',
        title: 'Two Sum',
        difficulty: 'Easy',
        description: 'Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.\n\nYou may assume that each input would have exactly one solution.',
        constraints: ['2 <= nums.length <= 10^4', '-10^9 <= nums[i] <= 10^9', 'Only one valid answer exists.'],
        starter_code: 'def twoSum(nums, target):\n    seen = {}\n    for i, num in enumerate(nums):\n        diff = target - num\n        if diff in seen:\n            return [seen[diff], i]\n        seen[num] = i\n    return []',
        sample_input: 'nums = [2, 7, 11, 15], target = 9',
        sample_output: '[0, 1]'
      },
      {
        id: 'dsa_2',
        title: 'LRU Cache Architecture',
        difficulty: 'Medium',
        description: 'Design a data structure that follows the constraints of a Least Recently Used (LRU) cache with O(1) operations.',
        constraints: ['capacity > 0', 'get and put must each run in O(1) average time complexity.'],
        starter_code: 'class LRUCache:\n    def __init__(self, capacity: int):\n        self.cap = capacity\n\n    def get(self, key: int) -> int:\n        return -1\n\n    def put(self, key: int, value: int) -> None:\n        pass',
        sample_input: '["LRUCache", "put", "put", "get"]',
        sample_output: '[null, null, null, 1]'
      },
      {
        id: 'dsa_3',
        title: 'Merge K Sorted Streams',
        difficulty: 'Hard',
        description: 'You are given an array of k linked-lists lists, each linked-list is sorted in ascending order. Merge all streams into one sorted stream.',
        constraints: ['0 <= k <= 10^4', '0 <= list length <= 500'],
        starter_code: 'def mergeKLists(lists):\n    pass',
        sample_input: 'lists = [[1,4,5],[1,3,4],[2,6]]',
        sample_output: '[1,1,2,3,4,4,5,6]'
      }
    ]);
  }

  if (url === '/api/coding/leaderboard') {
    return json([
      { rank: 1, username: 'Alex Johnson', score: 1480, problems_solved: 52 },
      { rank: 2, username: 'Elena Rostova', score: 1390, problems_solved: 48 },
      { rank: 3, username: 'David Chen', score: 1310, problems_solved: 43 },
      { rank: 4, username: 'Sophia Patel', score: 1180, problems_solved: 39 }
    ]);
  }

  if (url === '/api/admin/analytics') {
    return json({
      total_users: 184,
      total_interviews: 628,
      total_resumes_analyzed: 342,
      coding_submissions: 954,
      active_today: 37,
      chart_data: [
        { date: 'Nov 1', users: 145, interviews: 42 },
        { date: 'Nov 2', users: 152, interviews: 48 },
        { date: 'Nov 3', users: 160, interviews: 55 },
        { date: 'Nov 4', users: 168, interviews: 61 },
        { date: 'Nov 5', users: 174, interviews: 69 },
        { date: 'Nov 6', users: 179, interviews: 74 },
        { date: 'Nov 7', users: 184, interviews: 82 }
      ]
    });
  }

  if (url === '/api/admin/users') {
    return json({
      users: [
        { id: 'u1', name: 'Alex Johnson (Admin)', email: 'alex.johnson@prepai.dev', role: 'admin', is_verified: true, created_at: '2026-09-12', interviews_count: 14 },
        { id: 'u2', name: 'Sarah Connor', email: 'sarah.connor@cyberdyne.io', role: 'user', is_verified: true, created_at: '2026-10-01', interviews_count: 8 },
        { id: 'u3', name: 'Marcus Vance', email: 'marcus.v@cloudsystems.net', role: 'user', is_verified: true, created_at: '2026-10-18', interviews_count: 5 },
        { id: 'u4', name: 'Priya Sharma', email: 'priya.sharma@techglobal.in', role: 'user', is_verified: true, created_at: '2026-10-25', interviews_count: 11 }
      ]
    });
  }

  if (url.startsWith('/api/admin/ai/metrics')) {
    return json({
      period: 'today',
      total_requests: 532,
      total_tokens: 284190,
      cached_tokens: 105400,
      cache_hit_rate: '37.1%',
      avg_latency_ms: 1120,
      estimated_cost_usd: 0.54,
      models_used: {
        'gemini-1.5-flash': 482,
        'gemini-1.5-pro': 50
      }
    });
  }

  if (url.includes('/report')) {
    return json({
      report: {
        overall_score: 88,
        content_score: 90,
        delivery_score: 86,
        target_role: 'Senior Full-Stack Engineer',
        delivery_metrics: {
          voice_available: true,
          words_spoken: 620,
          wpm: 138,
          clarity: 89,
          eye_contact: 92
        },
        content_dimensions: {
          technical_accuracy: 9.1,
          depth: 8.8,
          clarity: 9.0,
          problem_solving: 8.7
        },
        answers: [
          {
            question: "How does React's virtual DOM reconciliation optimize UI rendering and avoid full-tree redraws?",
            answer: "React maintains an in-memory virtual DOM representation. During updates, the reconciliation algorithm diffs trees in O(n) heuristic complexity using stable element keys and batched Fiber work loops.",
            feedback: {
              score: 92,
              strengths: ["Clear explanation of heuristic O(n) diffing", "Detailed mention of key stability and fiber loops"],
              improvements: ["Could mention concurrent mode time-slicing"]
            }
          },
          {
            question: "Describe your architecture for handling high-concurrency real-time WebSocket state across clustered servers.",
            answer: "I decouple persistent WebSocket gateway connections behind an Nginx load balancer with sticky sessions, and use Redis Pub/Sub backplanes for horizontal broadcast across worker instances.",
            feedback: {
              score: 89,
              strengths: ["Excellent distributed Pub/Sub architecture", "Addresses sticky session requirements"],
              improvements: ["Consider discussing socket heartbeat reconnection backoffs"]
            }
          }
        ]
      }
    });
  }

  // Fallback 200 for other endpoints
  return json({ status: 'ok' });
});

// ── 2. Static Frontend Server on Port 5173 with SPA & Mock State Injected ──
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

const frontendServer = http.createServer((req, res) => {
  let reqPath = req.url.split('?')[0];
  let filePath = path.join(distDir, reqPath);
  const isDirectFile = fs.existsSync(filePath) && !fs.statSync(filePath).isDirectory();

  if (isDirectFile) {
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
    return res.end(fs.readFileSync(filePath));
  }

  // SPA fallback -> serve index.html with auto-injected state helper
  const indexPath = path.join(distDir, 'index.html');
  let html = fs.readFileSync(indexPath, 'utf8');

  const injection = `
  <script>
    (function() {
      try {
        const urlParams = new URLSearchParams(window.location.search);
        const auth = urlParams.get('mock_auth');
        if (auth === 'admin') {
          const adminUser = {
            id: 'u1',
            name: 'Alex Johnson',
            email: 'alex.johnson@prepai.dev',
            role: 'admin',
            bio: 'Senior Full Stack Engineer & Distributed Systems Architect.',
            github: 'alexjohnson-dev',
            linkedin: 'alex-johnson-tech',
            website: 'https://alexjohnson.dev',
            resume_filename: 'Alex_Johnson_Staff_Engineer_Resume.pdf'
          };
          localStorage.setItem('user', JSON.stringify(adminUser));
          localStorage.setItem('token', 'mock-jwt-token-2026');
        } else if (auth === 'none') {
          localStorage.removeItem('user');
          localStorage.removeItem('token');
        }

        if (urlParams.get('mock_results') === '1') {
          const mockResults = {
            score: 88,
            ats_score: 88,
            match_rate: "88%",
            strengths: [
              "Over 5 years of verified expertise across React, TypeScript, Node.js, and Distributed Systems",
              "Demonstrated scaling experience with high-throughput microservices (10M+ events/day)",
              "Strong technical education in Computer Science and clean, ATS-compliant formatting"
            ],
            improvements: [
              "Detail specific Kubernetes cluster management and CI/CD automation pipelines",
              "Add quantified test coverage metrics (e.g. Unit / Integration test suites with Jest & PyTest)"
            ],
            keywords_found: ["React", "TypeScript", "Node.js", "Python", "PostgreSQL", "AWS", "WebSockets", "Docker"],
            keywords_missing: ["Kubernetes", "GraphQL", "CI/CD", "Redis Caching"],
            sections_analyzed: {
              contact_info: "Complete & Verified",
              summary: "Executive & Impactful",
              experience: "Strong & Quantified",
              skills: "Well-Categorized",
              education: "Verified Degree"
            }
          };
          window.history.replaceState({
            usr: { results: mockResults, job_role: "Senior Full-Stack Engineer" }
          }, "");
        }

        if (urlParams.get('mock_diagnostic') === '1') {
          window.history.replaceState({
            usr: {
              session_id: "sess_diagnostic_01",
              question: {
                id: 1,
                title: "System Architecture & Resiliency",
                description: "Design a fault-tolerant message queue broker with zero data loss guarantee."
              },
              config: { role: "Senior Distributed Systems Engineer", intensity: 5 }
            }
          }, "");
        }
      } catch(e) { console.error('Mock script error:', e); }
    })();
  </script>
  </head>`;

  html = html.replace('</head>', injection);
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
});

// ── 3. Page Routes to Capture ──────────────────────────────────
const pagesToCapture = [
  { name: '01_landing', path: '/?mock_auth=none' },
  { name: '02_login', path: '/login?mock_auth=none' },
  { name: '03_signup', path: '/signup?mock_auth=none' },
  { name: '04_forgot_password', path: '/forgot-password?mock_auth=none' },
  { name: '05_reset_password', path: '/reset-password?mock_auth=none&token=demo-token-123' },
  { name: '06_verify_email', path: '/verify-email?mock_auth=none&token=demo-token-123' },
  { name: '07_onboarding', path: '/onboarding?mock_auth=admin' },
  { name: '08_dashboard', path: '/dashboard?mock_auth=admin' },
  { name: '09_profile', path: '/profile?mock_auth=admin' },
  { name: '10_resume_upload', path: '/resume/upload?mock_auth=admin' },
  { name: '11_resume_result', path: '/resume/result?mock_auth=admin&mock_results=1' },
  { name: '12_interview_setup', path: '/interview/setup?mock_auth=admin' },
  { name: '13_interview_diagnostic', path: '/interview/session?mock_auth=admin&mock_diagnostic=1' },
  { name: '14_interview_live', path: '/interview/live?mock_auth=admin' },
  { name: '15_interview_report', path: '/interview/report/sess_1?mock_auth=admin' },
  { name: '16_coding_dojo', path: '/coding/dojo?mock_auth=admin' },
  { name: '17_admin_dashboard', path: '/admin?mock_auth=admin' },
  { name: '18_admin_users', path: '/admin/users?mock_auth=admin' }
];

async function main() {
  await new Promise(r => apiServer.listen(5000, '127.0.0.1', r));
  console.log('✓ Mock API Server running on http://127.0.0.1:5000');

  await new Promise(r => frontendServer.listen(5173, '127.0.0.1', r));
  console.log('✓ Frontend Web Server running on http://127.0.0.1:5173');

  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const profileDir = 'D:\\Prep_AI\\chrome-capture-profile';

  console.log(`\n📸 Starting screenshot capture of all ${pagesToCapture.length} pages...`);

  for (let i = 0; i < pagesToCapture.length; i++) {
    const page = pagesToCapture[i];
    const outPath = path.join(screenshotsDir, `${page.name}.png`);
    const targetUrl = `http://127.0.0.1:5173${page.path}`;

    console.log(`[${i + 1}/${pagesToCapture.length}] Capturing ${page.name}...`);

    const chromeArgs = [
      `"${chromePath}"`,
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--virtual-time-budget=3500',
      `--user-data-dir="${profileDir}"`,
      '--window-size=1440,900',
      `--screenshot="${outPath}"`,
      `"${targetUrl}"`
    ].join(' ');

    try {
      execSync(chromeArgs, { stdio: 'pipe' });
      if (fs.existsSync(outPath)) {
        const stats = fs.statSync(outPath);
        console.log(`  ✓ Saved ${page.name}.png (${(stats.size / 1024).toFixed(1)} KB)`);
      } else {
        console.warn(`  ⚠️ File not created for ${page.name}`);
      }
    } catch (err) {
      console.error(`  ❌ Error capturing ${page.name}:`, err.message);
    }
  }

  // Cleanup profile
  try {
    fs.rmSync(profileDir, { recursive: true, force: true });
  } catch (e) {}

  console.log('\n🎉 All page screenshots captured successfully!');
  apiServer.close();
  frontendServer.close();
  process.exit(0);
}

main().catch(err => {
  console.error('Fatal execution error:', err);
  process.exit(1);
});

