import { useState } from 'react'
import ChatPage from './pages/ChatPage.jsx'
import ConsolePage from './pages/ConsolePage.jsx'

// 骨架期用简单 tab 切换两个受众(用户端 / 商家端)。将来可换 React Router + 独立部署。
// 注意:两个页面都常驻、用 CSS 显隐切换(不卸载)——否则切 tab 会销毁聊天状态与轮询,
// 结果回推就演示不出来。
export default function App() {
  const [tab, setTab] = useState('user')
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">🏍️ 摩托车售后智能助手</div>
        <nav className="tabs">
          <button className={tab === 'user' ? 'active' : ''} onClick={() => setTab('user')}>用户端</button>
          <button className={tab === 'merchant' ? 'active' : ''} onClick={() => setTab('merchant')}>商家端</button>
        </nav>
        <div className="env-tag">mock 后端</div>
      </header>
      <main className="content">
        <div className="pane" style={{ display: tab === 'user' ? 'flex' : 'none' }}><ChatPage /></div>
        <div className="pane" style={{ display: tab === 'merchant' ? 'block' : 'none' }}><ConsolePage /></div>
      </main>
    </div>
  )
}
