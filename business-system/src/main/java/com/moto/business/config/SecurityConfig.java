package com.moto.business.config;

import com.moto.business.security.JwtAuthFilter;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

import java.io.IOException;

/**
 * 鉴权总配置。无状态 JWT + 端点授权矩阵。
 * 授权分三类:①公开(登录注册)②角色受限(商家端点)③内部服务端点(仅 tool-service 内网调)。
 */
@Configuration
public class SecurityConfig {

    private final JwtAuthFilter jwtFilter;

    public SecurityConfig(JwtAuthFilter jwtFilter) {
        this.jwtFilter = jwtFilter;
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())     // 无状态 JWT 不吃 cookie,无 CSRF 面
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // ① 公开:注册/登录
                .requestMatchers("/auth/**").permitAll()
                // ② 商家端点:工单列表 + 裁决 —— 必须 MERCHANT(这就是原 /decide 裸奔的堵法)
                .requestMatchers(HttpMethod.GET, "/tickets").hasRole("MERCHANT")
                .requestMatchers(HttpMethod.POST, "/tickets/*/decide").hasRole("MERCHANT")
                // 用户端:查自己的工单(结果轮询),需登录
                .requestMatchers(HttpMethod.GET, "/tickets/*").authenticated()
                // ③ 内部服务端点(仅 tool-service 内网调,不对浏览器暴露):开工单/查订单/查槽位
                //    信任边界=内网。更严格做法:服务间鉴权,或把用户 token 透传到底让本系统自验(见 TODO)
                .requestMatchers(HttpMethod.POST, "/tickets").permitAll()
                .requestMatchers("/orders/**", "/slots/**").permitAll()
                .anyRequest().authenticated()
            )
            // 认证/授权失败的响应:未认证→401、已认证但角色不够→403,都回 JSON 提示。
            // 用 setStatus+write(不用 sendError)避免触发 /error 转发被自己二次拦截。
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((req, res, e) -> writeError(res, 401, "需要登录"))
                .accessDeniedHandler((req, res, e) -> writeError(res, 403, "无权限"))
            )
            // 把 JWT 过滤器插在用户名密码过滤器之前:先认令牌,再走授权
            .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    private static void writeError(HttpServletResponse res, int status, String msg) throws IOException {
        res.setStatus(status);
        res.setContentType("application/json;charset=UTF-8");
        res.getWriter().write("{\"error\":\"" + msg + "\"}");
    }

    /** 密码哈希器:BCrypt(自带盐、慢哈希抗爆破)。注册存哈希、登录用 matches 比对。 */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
