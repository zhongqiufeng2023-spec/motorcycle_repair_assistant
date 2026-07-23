package com.moto.business.service.impl;

import com.moto.business.entity.ServiceSlot;
import com.moto.business.repository.ServiceSlotRepository;
import com.moto.business.service.SlotService;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class SlotServiceImpl implements SlotService {

    private final ServiceSlotRepository repo;

    public SlotServiceImpl(ServiceSlotRepository repo) {
        this.repo = repo;
    }

    /** 查某天槽位;日期不在排班表里抛 IllegalArgumentException(→404)。 */
    @Override
    public ServiceSlot get(String date) {
        return repo.findById(date)
                .orElseThrow(() -> new IllegalArgumentException("该日期不在排班表: " + date));
    }

    @Override
    public List<ServiceSlot> listAll() {
        return repo.findAll();
    }

    @Override
    public List<ServiceSlot> listAvailable() {
        return repo.findByAvailableTrueOrderBySlotDate();
    }
}
