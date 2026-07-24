package com.moto.business.config;

import com.moto.business.entity.Order;
import com.moto.business.entity.Role;
import com.moto.business.entity.ServiceSlot;
import com.moto.business.entity.User;
import com.moto.business.repository.OrderRepository;
import com.moto.business.repository.ServiceSlotRepository;
import com.moto.business.repository.UserRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import java.util.List;

/**
 * 启动时灌参考数据(订单/槽位/账号),等价于原 Python 的 MOCK_ORDERS / MOCK_SLOTS + 内置账号。
 * 幂等:表非空就跳过,重启不重复插入。可复现(不像手动 SQL,进 git 就跟着走)。
 */
@Component
public class DataSeeder implements CommandLineRunner {

    private final OrderRepository orders;
    private final ServiceSlotRepository slots;
    private final UserRepository users;
    private final PasswordEncoder encoder;

    public DataSeeder(OrderRepository orders, ServiceSlotRepository slots,
                      UserRepository users, PasswordEncoder encoder) {
        this.orders = orders;
        this.slots = slots;
        this.users = users;
        this.encoder = encoder;
    }

    @Override
    public void run(String... args) {
        if (users.count() == 0) {
            // 商家账号种子:MERCHANT 不开放自助注册,只能这里灌(防随便注册个商家去批退款)
            users.save(new User("merchant", encoder.encode("merchant123"), Role.MERCHANT));
            // demo 顾客账号(顾客也能自己 /auth/register 注册,这条只是方便演示)
            users.save(new User("alice", encoder.encode("alice123"), Role.USER));
        }
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
