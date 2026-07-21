import { useState, useRef, useEffect } from 'react'
import { sendChat, getTicket } from '../api/mock.js'

// 用户聊天窗:发消息 → 显示气泡;退款类会返回工单号,并轮询工单状态,通过/驳回后把结果回推进对话。
export default function ChatPage() {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: '您好!我是摩托车售后助手,可以查保养参数、配件兼容、办理订单/退款等。有什么可以帮您?' },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const sessionId = useRef('web-' + Math.random().toString(36).slice(2, 8))
  const polling = useRef(new Set())
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  function pushMsg(m) { setMessages(prev => [...prev, m]) }

  // 轮询工单状态:PENDING → APPROVED/REJECTED 时,把结果作为一条新消息回推
  function watchTicket(ticketId) {
    if (polling.current.has(ticketId)) return
    polling.current.add(ticketId)
    const timer = setInterval(async () => {
      const t = await getTicket(ticketId)
      if (t && t.status !== 'PENDING') {
        clearInterval(timer)
        polling.current.delete(ticketId)
        pushMsg({
          role: 'assistant',
          text: t.status === 'APPROVED'
            ? `✅ 工单 ${t.id} 的退款已通过审核,将在 3-5 个工作日原路退回。`
            : `❌ 工单 ${t.id} 的退款申请未通过审核,已转人工客服跟进。`,
        })
      }
    }, 1500)
  }

  async function handleSend() {
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    pushMsg({ role: 'user', text: q })
    setBusy(true)
    try {
      const res = await sendChat(sessionId.current, q)
      pushMsg({ role: 'assistant', text: res.answer })
      if (res.status === 'pending_approval' && res.ticketId) watchTicket(res.ticketId)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat">
      <div className="chat-log">
        {messages.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role}`}>
            <div className={`bubble ${m.role}`}>{m.text}</div>
          </div>
        ))}
        {busy && <div className="bubble-row assistant"><div className="bubble assistant typing">正在思考…</div></div>}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="试试:火花塞多久换一次 / 订单12345我要退货"
        />
        <button onClick={handleSend} disabled={busy}>发送</button>
      </div>
    </div>
  )
}
