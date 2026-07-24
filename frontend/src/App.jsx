import { useState, useEffect } from 'react'
import ChatPage from './pages/ChatPage.jsx'
import ConsolePage from './pages/ConsolePage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import { getAuth, setAuth, clearAuth } from './auth.js'

// 登录门 + 角色路由:未登录→登录页;USER→用户聊天窗;MERCHANT→商家控制台。
// (不再用 tab 让谁都能看两端——现在按角色分流,更贴近真实系统;商家演示需另开一个浏览器/隐身窗登录 merchant。)
export default function App() {
  const [auth, setAuthState] = useState(getAuth())

  useEffect(() => {
    const onExpired = () => setAuthState(null)   // 401 时 backend.js 派发 → 回登录页
    window.addEventListener('auth-expired', onExpired)
    return () => window.removeEventListener('auth-expired', onExpired)
  }, [])

  function handleAuth(data) { setAuth(data); setAuthState(data) }
  function logout() { clearAuth(); setAuthState(null) }

  if (!auth) return <LoginPage onAuth={handleAuth} />

  const isMerchant = auth.role === 'MERCHANT'
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">🏍️ 摩托车售后智能助手</div>
        <div className="user-box">
          <span className="role-tag">{isMerchant ? '商家端' : '用户端'}</span>
          <span className="username">{auth.username}</span>
          <button className="logout-btn" onClick={logout}>登出</button>
        </div>
      </header>
      <main className="content">
        <div className="pane" style={{ display: isMerchant ? 'block' : 'flex' }}>
          {isMerchant ? <ConsolePage /> : <ChatPage />}
        </div>
      </main>
    </div>
  )
}
