package com.moto.business.dto;

import com.moto.business.entity.RefundStatus;
import com.moto.business.entity.RefundTicket;
import java.time.Instant;

/**
 * 对外响应 DTO(record,不可变)。实体不直接出网——序列化边界只过数据不过行为(DTO 纪律)。
 * 与前端 mock.js 的工单字段对齐,便于 mock→真实无缝切换。
 */
public record TicketResponse(
        Long id,
        String orderId,
        String sessionId,
        String reason,
        String itemName,
        RefundStatus status,
        String decisionNote,
        Instant createdAt,
        Instant updatedAt
) {
    /** 实体 → 响应 DTO 的映射。跨包调用,故 public。 */
    public static TicketResponse from(RefundTicket t) {
        return new TicketResponse(
                t.getId(), t.getOrderId(), t.getSessionId(), t.getReason(),
                t.getItemName(), t.getStatus(), t.getDecisionNote(),
                t.getCreatedAt(), t.getUpdatedAt());
    }
}
