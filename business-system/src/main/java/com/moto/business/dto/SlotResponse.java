package com.moto.business.dto;

import com.moto.business.entity.ServiceSlot;

/** 槽位响应 DTO。 */
public record SlotResponse(
        String slotDate,
        boolean available
) {
    public static SlotResponse from(ServiceSlot s) {
        return new SlotResponse(s.getSlotDate(), s.isAvailable());
    }
}
