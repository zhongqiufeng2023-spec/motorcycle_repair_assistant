package com.moto.business.entity;

import jakarta.persistence.*;

/**
 * 订单。二期:订单数据从 Python 的 MOCK_ORDERS 迁到业务系统,成为唯一权威;
 * Agent 侧 query_order / request_refund 改为 HTTP 查这里,不再各存一份。
 * 表名用 orders(order 是 SQL 保留字)。
 */
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private String orderNo;              // 订单号,纯数字字符串(业务主键,如 "12345")

    private String itemName;            // 商品名
    private String status;             // 物流状态:已签收 / 配送中

    private Integer daysSinceDelivery;  // 签收后天数(null=未签收);退款 7 天规则据此判

    protected Order() {}                // JPA 需要无参构造

    public Order(String orderNo, String itemName, String status, Integer daysSinceDelivery) {
        this.orderNo = orderNo;
        this.itemName = itemName;
        this.status = status;
        this.daysSinceDelivery = daysSinceDelivery;
    }

    public String getOrderNo() { return orderNo; }
    public String getItemName() { return itemName; }
    public String getStatus() { return status; }
    public Integer getDaysSinceDelivery() { return daysSinceDelivery; }
}
