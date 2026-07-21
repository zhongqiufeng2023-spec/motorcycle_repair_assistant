// ============================================================
// Mock 后端层 —— 前端骨架期用,定义的就是将来 Spring Boot 的接口契约。
// 两个界面(用户端 / 商家端)共用这一份内存工单 store,以此演示"工单化"全链路:
//   用户发退款 → 开工单(PENDING) → 商家审批 → 用户端轮询到结果回推。
// 接真后端时,把下面几个函数换成 fetch('/api/...') 即可,页面组件不用动。
// ============================================================

let _seq = 1000
const _tickets = []   // 内存工单表,对应 Spring Boot 的 refund_tickets

const delay = (ms = 400) => new Promise(r => setTimeout(r, ms))

// ---- 用户端:对话(对应 FastAPI /chat)----
// 返回 { status: 'done' | 'pending_approval', answer, ticketId? }
export async function sendChat(sessionId, question) {
  await delay()
  const isRefund = /退款|退货|退了|不想要/.test(question)
  if (isRefund) {
    const orderId = (question.match(/\d{4,}/) || ['(未提供)'])[0]
    const id = `T${++_seq}`
    _tickets.push({
      id, orderId, reason: question,
      status: 'PENDING', sessionId,
      userQuestion: question, createdAt: new Date().toISOString(),
    })
    return {
      status: 'pending_approval',
      ticketId: id,
      answer: `已为您提交退款申请(工单号 ${id},订单 ${orderId}),商家审核后会通知您。您可以继续咨询其他问题。`,
    }
  }
  // 非退款:骨架期给固定回复(接真后端后由 Agent 生成)
  return { status: 'done', answer: `【mock 回复】收到:"${question}"。接入 FastAPI 后这里会走真实检索与生成。` }
}

// ---- 商家端:工单列表(对应 Spring Boot GET /tickets)----
export async function listTickets() {
  await delay(200)
  return _tickets.slice().reverse()   // 新的在前
}

// ---- 商家端:审批(对应 Spring Boot POST /tickets/{id}/decide)----
export async function decideTicket(id, decision) {
  await delay()
  const t = _tickets.find(x => x.id === id)
  if (!t) return { ok: false, error: '工单不存在' }
  if (t.status !== 'PENDING') return { ok: false, error: '该工单已处理' }
  t.status = decision === 'approve' ? 'APPROVED' : 'REJECTED'
  t.decidedAt = new Date().toISOString()
  return { ok: true, ticket: { ...t } }
}

// ---- 用户端轮询单张工单状态(对应结果回推;真后端可换 WebSocket/SSE)----
export async function getTicket(id) {
  await delay(150)
  const t = _tickets.find(x => x.id === id)
  return t ? { ...t } : null
}
