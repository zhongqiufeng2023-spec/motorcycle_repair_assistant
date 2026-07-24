package com.moto.business.service.impl;

import com.moto.business.dto.AuthResponse;
import com.moto.business.entity.Role;
import com.moto.business.entity.User;
import com.moto.business.repository.UserRepository;
import com.moto.business.security.JwtUtil;
import com.moto.business.service.AuthService;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/** 认证业务逻辑:校验 + BCrypt 哈希 + 查库 + 签发 JWT(从 controller 下沉到这,便于单测/复用/与其它 service 一致)。 */
@Service
public class AuthServiceImpl implements AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtUtil jwt;

    public AuthServiceImpl(UserRepository users, PasswordEncoder encoder, JwtUtil jwt) {
        this.users = users;
        this.encoder = encoder;
        this.jwt = jwt;
    }

    @Override
    public AuthResponse register(String username, String password) {
        if (username == null || username.isBlank() || password == null || password.length() < 4)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "用户名不能为空,密码至少 4 位");
        if (users.existsByUsername(username))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "用户名已存在");
        // 密码 BCrypt 哈希后落库,永不存明文;注册只开放 USER 角色(商家由种子建)
        User u = users.save(new User(username, encoder.encode(password), Role.USER));
        return issue(u);
    }

    @Override
    public AuthResponse login(String username, String password) {
        User u = users.findByUsername(username).orElse(null);
        // 用户不存在与密码错误返回同一提示,不泄露"用户名是否存在"
        if (u == null || !encoder.matches(password, u.getPasswordHash()))
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "用户名或密码错误");
        return issue(u);
    }

    private AuthResponse issue(User u) {
        String token = jwt.generate(u.getId(), u.getUsername(), u.getRole().name());
        return new AuthResponse(token, u.getUsername(), u.getRole().name());
    }
}
