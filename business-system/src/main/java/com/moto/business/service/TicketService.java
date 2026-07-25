package com.moto.business.service;

import com.moto.business.entity.RefundStatus;
import com.moto.business.entity.RefundTicket;
import java.util.List;

/** 退款工单业务接口。实现见 service/impl/TicketServiceImpl。 */
public interface TicketService {

    /** 开单。幂等:同一订单已有待审工单则返回原单(agent 节点重放会重复调这里)。 */
    RefundTicket open(String orderId, String sessionId, String userId, String reason, String itemName);

    List<RefundTicket> list(RefundStatus status);

    RefundTicket get(Long id);

    RefundTicket decide(Long id, boolean approve, String note);
}
