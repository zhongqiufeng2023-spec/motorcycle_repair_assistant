package com.moto.business.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

/**
 * JWT 签发与校验。密钥来自配置 jwt.secret,FastAPI 用【同一把密钥】验同一个令牌
 * (无状态:两个后端不共享 session,共享的是密钥 + 算法)。
 */
@Component
public class JwtUtil {

    private final SecretKey key;
    private final long expirationMs;

    public JwtUtil(@Value("${jwt.secret}") String secret,
                   @Value("${jwt.expiration-ms}") long expirationMs) {
        // ⚠️ 算法不是写死的,是 hmacShaKeyFor 按密钥【字节长度】推出来的:
        //    ≥32B→HS256,≥48B→HS384,≥64B→HS512(不足 32B 直接抛 WeakKeyException)。
        //    默认串 53 字节 → 实际签发用 HS384,而 app/api.py 把 JWT_ALG 写死成 "HS384"。
        //    所以换 JWT_SECRET 时【长度不能跌破 48 字节】,否则这边改用 HS256 签、
        //    Python 那边只认 HS384 → 全部请求 401,且报错不会指向密钥长度。
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expirationMs = expirationMs;
    }

    /** 签发:subject=userId,附 username 与 role(前端/FastAPI 直接读,不必再查库)。 */
    public String generate(Long userId, String username, String role) {
        Date now = new Date();
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .claim("role", role)
                .issuedAt(now)
                .expiration(new Date(now.getTime() + expirationMs))
                .signWith(key)
                .compact();
    }

    /** 校验签名+有效期并取出 claims;失败(签名不符/过期/格式错)抛 JwtException,由过滤器兜底。 */
    public Claims parse(String token) {
        return Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
    }
}
