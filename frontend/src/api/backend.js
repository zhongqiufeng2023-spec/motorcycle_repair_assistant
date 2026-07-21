// ============================================================
// 真后端层 —— 调 FastAPI Agent 服务。
// 前端 fetch('/api/...'),由 vite dev 代理转发到 http://localhost:8000(见 vite.config.js),
// 浏览器视角同源、无需 CORS。函数签名与 mock.js 对齐 → 页面组件换 import 即可切换。
// ============================================================

async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path} 返回 ${res.status}`)
  return res.json()
}

// 归一化 FastAPI ChatResponse( { status, answer, question, options, approval_request } )
function norm(d) {
  return { status: d.status, answer: d.answer, question: d.question, options: d.options, ticketId: undefined }
}

// 用户提问(对应 FastAPI /chat)
export async function sendChat(sessionId, question) {
  return norm(await post('/api/chat', { session_id: sessionId, question }))
}

// 对挂起点的回答(对应 FastAPI /resume):澄清补充信息走这里。
// 关键:走 /resume → Command(resume) → 直接送回等待的 interrupt(),不经过路由——
// 所以"是""12345"这类裸回复不会被路由误判。
export async function resumeChat(sessionId, value) {
  return norm(await post('/api/resume', { session_id: sessionId, value }))
}
