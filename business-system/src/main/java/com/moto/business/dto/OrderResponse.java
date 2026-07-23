package com.moto.business.dto;

import com.moto.business.entity.Order;

/** 订单响应 DTO。字段名对齐 Agent 侧 query_order 的老返回(item/status/days_since_delivery)。 */
public record OrderResponse(
        String orderNo,
        String itemName,
        String status,
        Integer daysSinceDelivery
) {
    public static OrderResponse from(Order o) {
        return new OrderResponse(o.getOrderNo(), o.getItemName(), o.getStatus(), o.getDaysSinceDelivery());
    }
}
