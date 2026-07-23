package com.moto.business.service;

import com.moto.business.entity.ServiceSlot;
import java.util.List;

/** 预约槽位业务接口。实现见 service/impl/SlotServiceImpl。 */
public interface SlotService {

    ServiceSlot get(String date);

    List<ServiceSlot> listAll();

    List<ServiceSlot> listAvailable();
}
