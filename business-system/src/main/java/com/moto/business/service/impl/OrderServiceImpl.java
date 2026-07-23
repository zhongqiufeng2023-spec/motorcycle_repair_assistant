package com.moto.business.service.impl;

import com.moto.business.entity.Order;
import com.moto.business.repository.OrderRepository;
import com.moto.business.service.OrderService;
import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {

    private final OrderRepository repo;

    public OrderServiceImpl(OrderRepository repo) {
        this.repo = repo;
    }

    /** 查订单;不存在抛 IllegalArgumentException(由 ApiExceptionHandler 翻成 404)。 */
    @Override
    public Order get(String orderNo) {
        return repo.findById(orderNo)
                .orElseThrow(() -> new IllegalArgumentException("订单不存在: " + orderNo));
    }
}
