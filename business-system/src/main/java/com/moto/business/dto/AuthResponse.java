package com.moto.business.dto;

/** 认证成功响应:JWT + 用户名 + 角色(前端存起来,后续请求带 token)。 */
public record AuthResponse(String token, String username, String role) {}
