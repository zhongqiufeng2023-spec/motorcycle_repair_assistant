package com.moto.business.service.impl;

import com.moto.business.entity.RefundStatus;
import com.moto.business.entity.RefundTicket;
import com.moto.business.repository.RefundTicketRepository;
import com.moto.business.service.TicketService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

/** 工单业务逻辑 + 状态机。业务规则的唯一权威(退款 7 天、执行退款都住这)。 */
@Service
public class TicketServiceImpl implements TicketService {

    private final RefundTicketRepository repo;

    public TicketServiceImpl(RefundTicketRepository repo) {
        this.repo = repo;
    }

    /** 开单:agent 的 request_refund 工具调这里,取代原 interrupt。落库即 PENDING。 */
    @Override
    @Transactional
    public RefundTicket open(String orderId, String sessionId, String userId, String reason, String itemName) {
        RefundTicket t = new RefundTicket();
        t.setOrderId(orderId);
        t.setSessionId(sessionId);
        t.setUserId(userId);
        t.setReason(reason);
        t.setItemName(itemName);
        t.setStatus(RefundStatus.PENDING);
        return repo.save(t);
    }

    /** 列表:status 为 null 取全部,否则按状态过滤(商家台默认看 PENDING)。 */
    @Override
    public List<RefundTicket> list(RefundStatus status) {
        return status == null
                ? repo.findAllByOrderByCreatedAtDesc()
                : repo.findByStatusOrderByCreatedAtDesc(status);
    }

    /** 单条:用户端轮询结果用。 */
    @Override
    public RefundTicket get(Long id) {
        return repo.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("工单不存在: " + id));
    }

    /**
     * 裁决:商家通过/驳回。状态机守卫:只有 PENDING 可裁决,防重复处理。
     * 通过则【确定性执行退款(无 LLM)】——这正是工单化要的:执行权在业务系统,不在会被重放的 LLM。
     */
    @Override
    @Transactional
    public RefundTicket decide(Long id, boolean approve, String note) {
        RefundTicket t = get(id);
        if (t.getStatus() != RefundStatus.PENDING) {
            throw new IllegalStateException("工单已处理(" + t.getStatus() + "),不能重复裁决");
        }
        if (approve) {
            executeRefund(t);
            t.setStatus(RefundStatus.APPROVED);
        } else {
            t.setStatus(RefundStatus.REJECTED);
        }
        t.setDecisionNote(note);
        return repo.save(t);
    }

    /** mock:真实系统这里调支付网关退款。演示只打日志(执行是确定性的,可重试幂等)。 */
    private void executeRefund(RefundTicket t) {
        System.out.println("[退款执行] 工单#" + t.getId() + " 订单 " + t.getOrderId() + " 退款已发起(mock)");
    }
}
