package com.moto.business.service;

import com.moto.business.dto.AuthResponse;

/** 认证业务接口。实现见 service/impl/AuthServiceImpl。 */
public interface AuthService {

    /** 注册(仅创建 USER),成功返回已签发的令牌。 */
    AuthResponse register(String username, String password);

    /** 登录,校验密码后返回令牌。 */
    AuthResponse login(String username, String password);
}
