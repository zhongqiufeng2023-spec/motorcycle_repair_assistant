import { useState, useRef, useEffect } from 'react'
import { sendChat, resumeChat } from '../api/backend.js'
import { getTicket } from '../api/mock.js'

// 用户聊天窗:普通问答走 /chat;当后端返回 pending_clarification(缺信息追问)时,进入"等补充"状态,
// 用户下一条走 /resume(绕过路由,直接送回等待的 interrupt)——根治裸回复("是"/"12345")被路由误判。
export default function ChatPage() {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: '您好!我是摩托车售后助手,可以查保养参数、配件兼容、办理订单/退款等。有什么可以帮您?' },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [clarify, setClarify] = useState(null)   // null | { options: string[] | null } —— 非 null 表示正在等用户补充
  const sessionId = useRef('web-' + Math.random().toString(36).slice(2, 8))
  const polling = useRef(new Set())
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  function pushMsg(m) { setMessages(prev => [...prev, m]) }

  // 退款工单轮询回推(mock 阶段;退款工单化后改查 Spring Boot)
  function watchTicket(ticketId) {
    if (polling.current.has(ticketId)) return
    polling.current.add(ticketId)
    const timer = setInterval(async () => {
      const t = await getTicket(ticketId)
      if (t && t.status !== 'PENDING') {
        clearInterval(timer)
        polling.current.delete(ticketId)
        pushMsg({ role: 'assistant', text: t.status === 'APPROVED'
          ? `✅ 工单 ${t.id} 的退款已通过审核,将在 3-5 个工作日原路退回。`
          : `❌ 工单 ${t.id} 的退款申请未通过审核,已转人工客服跟进。` })
      }
    }, 1500)
  }

  function handleResponse(res) {
    pushMsg({ role: 'assistant', text: res.answer || res.question })
    if (res.status === 'pending_clarification') {
      setClarify({ options: res.options || null })   // 进入"等补充"——下一条走 /resume
    } else {
      setClarify(null)
      if (res.status === 'pending_approval' && res.ticketId) watchTicket(res.ticketId)
    }
  }

  async function submit(text) {
    if (!text || busy) return
    pushMsg({ role: 'user', text })
    setBusy(true)
    try {
      // 正在等澄清补充 → /resume(绕路由);否则 → /chat
      const res = clarify ? await resumeChat(sessionId.current, text) : await sendChat(sessionId.current, text)
      handleResponse(res)
    } catch (e) {
      pushMsg({ role: 'assistant', text: '⚠️ 无法连接后端服务,请确认 FastAPI 已在 :8000 运行(uvicorn app.api:app --port 8000)。' })
    } finally {
      setBusy(false)
    }
  }

  function handleSend() { const q = input.trim(); setInput(''); submit(q) }

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

      {clarify?.options && (
        <div className="options">
          {clarify.options.map(o => (
            <button key={o} className="option-btn" disabled={busy} onClick={() => { setInput(''); submit(o) }}>{o}</button>
          ))}
        </div>
      )}

      <div className="chat-input">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={clarify ? '请补充上面问题所需的信息…' : '试试:火花塞多久换一次 / 帮我查订单状态'}
        />
        <button onClick={handleSend} disabled={busy}>发送</button>
      </div>
    </div>
  )
}
