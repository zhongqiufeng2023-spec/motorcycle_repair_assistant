package com.moto.business.entity;

import jakarta.persistence.*;
import java.time.Instant;

/**
 * 退款工单。二期核心:把"审批"从对话的 interrupt 暂停键,变成一张独立、持久、有状态机的工单。
 * 对话线程开完单立刻结束(不挂起);商家在业务系统裁决;结果异步推回对话。
 */
@Entity
@Table(name = "refund_tickets")
public class RefundTicket {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderId;      // 要退款的订单号
    private String sessionId;    // 发起会话(推回哪段对话)
    private String userId;       // 发起用户(JWT subject);谁的退款、谁能查。历史工单可能为空

    @Column(length = 500)
    private String reason;       // 退款原因(用户话术)
    private String itemName;     // 冗余展示:商品名,开单时由 agent 带入,省得商家再查

    @Enumerated(EnumType.STRING) // 存字符串而非序号,枚举增删不错位
    @Column(nullable = false, length = 20)
    private RefundStatus status = RefundStatus.PENDING;

    @Column(length = 500)
    private String decisionNote; // 商家裁决备注

    @Column(nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    @Column(nullable = false)
    private Instant updatedAt = Instant.now();

    @PreUpdate
    void touch() {
        this.updatedAt = Instant.now();
    }

    // --- getters / setters(不引入 Lombok,减少注解处理器这一层依赖)---
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }

    public String getItemName() { return itemName; }
    public void setItemName(String itemName) { this.itemName = itemName; }

    public RefundStatus getStatus() { return status; }
    public void setStatus(RefundStatus status) { this.status = status; }

    public String getDecisionNote() { return decisionNote; }
    public void setDecisionNote(String decisionNote) { this.decisionNote = decisionNote; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
