package com.moto.business.exception;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
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
}
