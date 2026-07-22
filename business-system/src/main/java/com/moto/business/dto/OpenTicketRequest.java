package com.moto.business.dto;

/** 开单请求体(agent 的 request_refund 工具带入)。 */
public record OpenTicketRequest(
        String orderId,
        String sessionId,
        String reason,
        String itemName
) {}
