import { useState, useEffect, useCallback } from 'react'
import { listTickets, decideTicket } from '../api/backend.js'

const STATUS_LABEL = { PENDING: '待审核', APPROVED: '已通过', REJECTED: '已驳回' }

// 商家审批控制台:列出退款工单,对 PENDING 的通过/驳回。轮询刷新以看到用户端新提交的工单。
export default function ConsolePage() {
  const [tickets, setTickets] = useState([])
  const [acting, setActing] = useState(null)

  const refresh = useCallback(async () => setTickets(await listTickets()), [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 2000)   // 轮询:用户端新开的工单会冒出来
    return () => clearInterval(timer)
  }, [refresh])

  async function decide(id, decision) {
    setActing(id)
    await decideTicket(id, decision)
    await refresh()
    setActing(null)
  }

  const pending = tickets.filter(t => t.status === 'PENDING')
  const handled = tickets.filter(t => t.status !== 'PENDING')

  return (
    <div className="console">
      <section>
        <h3>待审核 <span className="count">{pending.length}</span></h3>
        {pending.length === 0 && <p className="empty">暂无待审核工单。去「用户端」发一条"订单12345我要退货"试试。</p>}
        {pending.map(t => (
          <div key={t.id} className="ticket">
            <div className="ticket-main">
              <div className="ticket-id">{t.id} <span className="tag warn">退款</span></div>
              <div className="ticket-field">订单号:{t.orderId}</div>
              <div className="ticket-field">商品:{t.itemName}</div>
              <div className="ticket-field">退款原因:{t.reason}</div>
              <div className="ticket-time">{new Date(t.createdAt).toLocaleString('zh-CN')}</div>
            </div>
            <div className="ticket-actions">
              <button className="btn approve" disabled={acting === t.id} onClick={() => decide(t.id, 'approve')}>通过</button>
              <button className="btn reject" disabled={acting === t.id} onClick={() => decide(t.id, 'reject')}>驳回</button>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h3>已处理 <span className="count">{handled.length}</span></h3>
        {handled.map(t => (
          <div key={t.id} className="ticket done">
            <div className="ticket-main">
              <div className="ticket-id">{t.id}
                <span className={`tag ${t.status === 'APPROVED' ? 'ok' : 'bad'}`}>{STATUS_LABEL[t.status]}</span>
              </div>
              <div className="ticket-field">订单号:{t.orderId}</div>
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}
