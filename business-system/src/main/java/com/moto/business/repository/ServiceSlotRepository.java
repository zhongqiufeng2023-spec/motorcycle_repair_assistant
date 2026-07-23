package com.moto.business.repository;

import com.moto.business.entity.ServiceSlot;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ServiceSlotRepository extends JpaRepository<ServiceSlot, String> {

    List<ServiceSlot> findByAvailableTrueOrderBySlotDate();   // 所有可约日期(升序)
}
