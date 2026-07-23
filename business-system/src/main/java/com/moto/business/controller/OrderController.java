package com.moto.business.controller;

import com.moto.business.dto.OrderResponse;
import com.moto.business.service.OrderService;
import org.springframework.web.bind.annotation.*;

/** 订单查询端点。Agent 侧 query_order / request_refund 预检来这里查。 */
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    /** GET /orders/{orderNo} —— 不存在返回 404 */
    @GetMapping("/{orderNo}")
    public OrderResponse get(@PathVariable String orderNo) {
        return OrderResponse.from(service.get(orderNo));
    }
}
