package com.moto.business.config;

import com.moto.business.entity.Order;
import com.moto.business.entity.ServiceSlot;
import com.moto.business.repository.OrderRepository;
import com.moto.business.repository.ServiceSlotRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;
import java.util.List;

/**
 * 启动时灌参考数据(订单/槽位),等价于原 Python 的 MOCK_ORDERS / MOCK_SLOTS。
 * 幂等:表非空就跳过,重启不重复插入。可复现(不像手动 SQL,进 git 就跟着走)。
 */
@Component
public class DataSeeder implements CommandLineRunner {

    private final OrderRepository orders;
    private final ServiceSlotRepository slots;

    public DataSeeder(OrderRepository orders, ServiceSlotRepository slots) {
        this.orders = orders;
        this.slots = slots;
    }

    @Override
    public void run(String... args) {
        if (orders.count() == 0) {
            orders.saveAll(List.of(
                    new Order("12345", "NGK CPR8EA-9 火花塞", "已签收", 3),
                    new Order("12346", "DID 520 链条", "配送中", null),   // 未签收
                    new Order("12347", "DOT4 刹车油", "已签收", 15)        // 超7天,退款会被拒
            ));
        }
        if (slots.count() == 0) {
            slots.saveAll(List.of(
                    new ServiceSlot("2026-07-18", false),  // 已满
                    new ServiceSlot("2026-07-19", true),
                    new ServiceSlot("2026-07-20", true)
            ));
        }
    }
}
