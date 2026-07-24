import { useState } from 'react'
import { login, register } from '../api/backend.js'

// 登录 / 注册页。注册只创建普通用户(USER);商家账号由后台种子建,不自助注册。
export default function LoginPage({ onAuth }) {
  const [mode, setMode] = useState('login')     // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      const fn = mode === 'login' ? login : register
      const data = await fn(username.trim(), password)   // {token, username, role}
      onAuth(data)
    } catch (e) {
      setErr(e.message || '出错了')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">🏍️ 摩托车售后智能助手</div>
        <div className="auth-title">{mode === 'login' ? '登录' : '注册新账号'}</div>
        <input placeholder="用户名" value={username} onChange={e => setUsername(e.target.value)} autoFocus />
        <input type="password" placeholder="密码(至少 4 位)" value={password} onChange={e => setPassword(e.target.value)} />
        {err && <div className="auth-err">{err}</div>}
        <button type="submit" disabled={busy || !username || !password}>
          {busy ? '请稍候…' : (mode === 'login' ? '登录' : '注册并登录')}
        </button>
        <div className="auth-switch">
          {mode === 'login'
            ? <>还没账号?<a onClick={() => { setMode('register'); setErr('') }}>去注册</a></>
            : <>已有账号?<a onClick={() => { setMode('login'); setErr('') }}>去登录</a></>}
        </div>
        <div className="auth-hint">演示账号 —— 商家:merchant / merchant123 · 顾客:alice / alice123</div>
      </form>
    </div>
  )
}
