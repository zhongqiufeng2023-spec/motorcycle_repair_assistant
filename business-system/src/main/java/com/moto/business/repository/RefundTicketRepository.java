package com.moto.business.repository;

import com.moto.business.entity.RefundStatus;
import com.moto.business.entity.RefundTicket;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

/** Spring Data JPA:方法名即查询。crud 由 JpaRepository 白送。 */
public interface RefundTicketRepository extends JpaRepository<RefundTicket, Long> {

    List<RefundTicket> findAllByOrderByCreatedAtDesc();                        // 全部,新的在前

    List<RefundTicket> findByStatusOrderByCreatedAtDesc(RefundStatus status);  // 按状态过滤(商家台看 PENDING)

    // 幂等开单用:同一订单当前是否已有待审工单。用 First 而非唯一返回,是因为
    // 唯一性由数据库的部分唯一索引保证(见 config/SchemaGuards),这里不该因为
    // 历史脏数据里恰好有两张就抛 IncorrectResultSizeDataAccessException。
    Optional<RefundTicket> findFirstByOrderIdAndStatusOrderByIdAsc(String orderId, RefundStatus status);
}
