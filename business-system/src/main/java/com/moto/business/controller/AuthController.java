package com.moto.business.controller;

import com.moto.business.dto.AuthRequest;
import com.moto.business.dto.AuthResponse;
import com.moto.business.service.AuthService;
import org.springframework.web.bind.annotation.*;

/** 认证端点(公开)。薄控制器:只做 HTTP 映射,业务全在 AuthService。失败异常交 ApiExceptionHandler。 */
@RestController
@RequestMapping("/auth")
public class AuthController {

    private final AuthService auth;

    public AuthController(AuthService auth) {
        this.auth = auth;
    }

    @PostMapping("/register")
    public AuthResponse register(@RequestBody AuthRequest req) {
        return auth.register(req.username(), req.password());
    }

    @PostMapping("/login")
    public AuthResponse login(@RequestBody AuthRequest req) {
        return auth.login(req.username(), req.password());
    }
}
