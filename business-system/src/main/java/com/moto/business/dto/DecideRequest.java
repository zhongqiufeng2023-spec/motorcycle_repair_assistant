package com.moto.business.dto;

/** 裁决请求体:decision = "approve" | "reject",note 为商家备注(可选)。 */
public record DecideRequest(
        String decision,
        String note
) {}
