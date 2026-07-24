// 登录态:token + 用户信息存 localStorage(刷新不丢,重连不必重登)。
// token 是 Spring Boot 签发的 JWT;FastAPI 与 Spring Boot 用同一密钥各自校验。
const KEY = 'moto_auth'

export function getAuth() {
  try { return JSON.parse(localStorage.getItem(KEY)) } catch { return null }
}
export function setAuth(auth) { localStorage.setItem(KEY, JSON.stringify(auth)) }
export function clearAuth() { localStorage.removeItem(KEY) }
export function getToken() { return getAuth()?.token || null }
