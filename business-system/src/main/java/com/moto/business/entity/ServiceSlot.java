package com.moto.business.entity;

import jakarta.persistence.*;

/**
 * 保养预约槽位。二期:从 Python 的 MOCK_SLOTS 迁来。
 * 只读可约状态(当前不落"预约记录",与原 mock 行为一致;真持久化预约留后续)。
 */
@Entity
@Table(name = "service_slots")
public class ServiceSlot {

    @Id
    private String slotDate;    // 日期,格式 2026-07-18(业务主键)

    private boolean available;  // 是否可约(false=已满)

    protected ServiceSlot() {}

    public ServiceSlot(String slotDate, boolean available) {
        this.slotDate = slotDate;
        this.available = available;
    }

    public String getSlotDate() { return slotDate; }
    public boolean isAvailable() { return available; }
}
