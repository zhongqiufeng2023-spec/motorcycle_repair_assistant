package com.moto.business.service;

import com.moto.business.entity.Order;

/** 订单查询业务接口。实现见 service/impl/OrderServiceImpl。 */
public interface OrderService {

    Order get(String orderNo);
}
