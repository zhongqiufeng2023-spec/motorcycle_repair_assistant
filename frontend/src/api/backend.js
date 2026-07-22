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
  return { status: d.status, answer: d.answer, question: d.question, options: d.options, ticketId: d.ticket_id }
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

// ---- 工单(对应 Spring Boot 业务系统,经 vite 代理 /api/tickets → :8080)----

// 工单列表(商家台);后端已按 createdAt 倒序返回,无需再 reverse
export async function listTickets() {
  const res = await fetch('/api/tickets')
  if (!res.ok) throw new Error(`/api/tickets 返回 ${res.status}`)
  return res.json()
}

// 裁决工单(通过/驳回);签名与 mock 对齐,返回 { ok, ticket } 或 { ok:false, error }
export async function decideTicket(id, decision, note = '') {
  const res = await fetch(`/api/tickets/${id}/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note }),
  })
  const data = await res.json()
  return res.ok ? { ok: true, ticket: data } : { ok: false, error: data.error }
}

// 单张工单(用户端轮询结果回推用)
export async function getTicket(id) {
  const res = await fetch(`/api/tickets/${id}`)
  return res.ok ? res.json() : null
}
