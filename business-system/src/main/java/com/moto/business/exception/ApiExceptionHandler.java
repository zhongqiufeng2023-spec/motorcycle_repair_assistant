package com.moto.business.exception;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;
import java.util.Map;

/** 把 service 抛的业务异常翻成规范 HTTP 状态,别让调用方吃 500。 */
@RestControllerAdvice
public class ApiExceptionHandler {

    /** 工单不存在 → 404 */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> notFound(IllegalArgumentException e) {
        return ResponseEntity.status(404).body(Map.of("error", e.getMessage()));
    }

    /** 状态机违规(重复裁决已处理工单) → 409 Conflict */
    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> conflict(IllegalStateException e) {
        return ResponseEntity.status(409).body(Map.of("error", e.getMessage()));
    }

    /** 带状态码的业务异常(如 AuthService 的 400/401/409)→ 原状态 + JSON。
     *  用 @ExceptionHandler 直接返回 ResponseEntity,避开默认 sendError 触发 /error 转发被 Security 二次拦成 403。 */
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> statusException(ResponseStatusException e) {
        String msg = e.getReason() != null ? e.getReason() : "请求失败";
        return ResponseEntity.status(e.getStatusCode()).body(Map.of("error", msg));
    }
}
