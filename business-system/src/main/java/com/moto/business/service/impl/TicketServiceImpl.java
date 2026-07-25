package com.moto.business.service.impl;

import com.moto.business.entity.RefundStatus;
import com.moto.business.entity.RefundTicket;
import com.moto.business.repository.RefundTicketRepository;
import com.moto.business.service.TicketService;
import org.springframework.dao.DataIntegrityViolationException;
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

    /**
     * 开单:agent 的 request_refund 工具调这里,取代原 interrupt。落库即 PENDING。
     *
     * <p><b>幂等</b>:同一订单已有待审工单就返回那一张,不再开新单。原因是 agent 的
     * action_node 含 interrupt(澄清追问),恢复时节点从头重放,排在挂起点之前的
     * request_refund 会被再执行一遍。幂等只能落在这里——agent 被 interrupt 打断时
     * 连 state 都没提交过,记不住"我已经开过单了"。约束本身见 config/SchemaGuards。
     *
     * <p><b>这里故意不加 {@code @Transactional}</b>:若整个方法包在一个事务里,save 撞上
     * 唯一索引后事务已被标记 rollback-only、Postgres 连接进入 aborted 状态,catch 里再查库
     * 会直接报 "current transaction is aborted"。不加事务时,save 走 Spring Data 自带的
     * 那层事务、失败即独立回滚,catch 里的查询是一个全新事务,才看得到别人刚提交的那张单。
     */
    @Override
    public RefundTicket open(String orderId, String sessionId, String userId, String reason, String itemName) {
        // 快路径:节点重放是串行的,先查一下就能挡住,不必等约束抛异常(也免得日志天天飘红)
        var existing = repo.findFirstByOrderIdAndStatusOrderByIdAsc(orderId, RefundStatus.PENDING);
        if (existing.isPresent()) {
            return existing.get();
        }
        RefundTicket t = new RefundTicket();
        t.setOrderId(orderId);
        t.setSessionId(sessionId);
        t.setUserId(userId);
        t.setReason(reason);
        t.setItemName(itemName);
        t.setStatus(RefundStatus.PENDING);
        try {
            return repo.save(t);
        } catch (DataIntegrityViolationException e) {
            // 并发:两个请求同时穿过上面那一查(TOCTOU)。部分唯一索引挡下后到者,
            // 这里回头把先到者那张单取出来返回——对调用方而言仍是"开单成功",单号一致。
            return repo.findFirstByOrderIdAndStatusOrderByIdAsc(orderId, RefundStatus.PENDING)
                    .orElseThrow(() -> e);   // 查不到说明不是撞这个约束(如索引没建上),别把异常吞了
        }
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
