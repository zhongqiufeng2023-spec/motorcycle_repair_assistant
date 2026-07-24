// ============================================================
// 真后端层 —— 调 FastAPI Agent(:8000)与 Spring Boot 业务系统(:8080)。
// 受保护请求带 Authorization: Bearer <JWT>(登录后从 localStorage 取)。
// 401=登录失效:清 token + 派发 auth-expired 事件,App 据此回登录页。
// vite 代理:/api/auth /api/tickets → :8080(Spring Boot),其余 /api/* → :8000(FastAPI)。
// ============================================================
import { getToken, clearAuth } from '../auth.js'

function authHeaders() {
  const h = { 'Content-Type': 'application/json' }
  const t = getToken()
  if (t) h.Authorization = `Bearer ${t}`
  return h
}

// 401 统一处理:令牌无效/过期 → 登出回登录页
function guard(res) {
  if (res.status === 401) {
    clearAuth()
    window.dispatchEvent(new Event('auth-expired'))
    throw new Error('登录已失效,请重新登录')
  }
  return res
}

async function postAuthed(path, body) {
  const res = guard(await fetch(path, { method: 'POST', headers: authHeaders(), body: JSON.stringify(body) }))
  if (!res.ok) throw new Error(`${path} 返回 ${res.status}`)
  return res.json()
}

// ---- 认证(Spring Boot /auth/**;登录/注册本身不带 token)----
async function postAuth(path, body) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `请求失败(${res.status})`)
  return data   // {token, username, role}
}
export const login = (username, password) => postAuth('/api/auth/login', { username, password })
export const register = (username, password) => postAuth('/api/auth/register', { username, password })

// ---- 对话(FastAPI /chat /resume)----
function norm(d) {
  return { status: d.status, answer: d.answer, question: d.question, options: d.options, ticketId: d.ticket_id }
}
export async function sendChat(sessionId, question) {
  return norm(await postAuthed('/api/chat', { session_id: sessionId, question }))
}
export async function resumeChat(sessionId, value) {
  return norm(await postAuthed('/api/resume', { session_id: sessionId, value }))
}

// ---- 工单(Spring Boot /tickets)----
export async function listTickets() {
  const res = guard(await fetch('/api/tickets', { headers: authHeaders() }))
  if (!res.ok) throw new Error(`/api/tickets 返回 ${res.status}`)
  return res.json()
}
export async function decideTicket(id, decision, note = '') {
  const res = guard(await fetch(`/api/tickets/${id}/decide`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify({ decision, note }) }))
  const data = await res.json().catch(() => ({}))
  return res.ok ? { ok: true, ticket: data } : { ok: false, error: data.error }
}
export async function getTicket(id) {
  const res = guard(await fetch(`/api/tickets/${id}`, { headers: authHeaders() }))
  return res.ok ? res.json() : null
}
