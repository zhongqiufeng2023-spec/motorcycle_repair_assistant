package com.moto.business.entity;

/** 退款工单状态机的三态。PENDING 为初态;裁决后进 APPROVED(已执行退款)或 REJECTED。 */
public enum RefundStatus {
    PENDING,    // 待商家审核
    APPROVED,   // 已通过(退款已确定性执行)
    REJECTED    // 已驳回
}
