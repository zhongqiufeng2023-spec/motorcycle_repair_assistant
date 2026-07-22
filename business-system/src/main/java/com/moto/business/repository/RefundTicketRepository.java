package com.moto.business.repository;

import com.moto.business.entity.RefundStatus;
import com.moto.business.entity.RefundTicket;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

/** Spring Data JPA:方法名即查询。crud 由 JpaRepository 白送。 */
public interface RefundTicketRepository extends JpaRepository<RefundTicket, Long> {

    List<RefundTicket> findAllByOrderByCreatedAtDesc();                        // 全部,新的在前

    List<RefundTicket> findByStatusOrderByCreatedAtDesc(RefundStatus status);  // 按状态过滤(商家台看 PENDING)
}
