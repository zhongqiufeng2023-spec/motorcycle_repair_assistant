package com.moto.business.controller;

import com.moto.business.dto.DecideRequest;
import com.moto.business.dto.OpenTicketRequest;
import com.moto.business.dto.TicketResponse;
import com.moto.business.entity.RefundStatus;
import com.moto.business.service.TicketService;
import org.springframework.web.bind.annotation.*;
import java.util.List;

/** 工单 REST 端点。前端 vite 代理 /api/tickets → 这里(:8080)。 */
@RestController
@RequestMapping("/tickets")
public class TicketController {

    private final TicketService service;

    public TicketController(TicketService service) {
        this.service = service;
    }

    /** 开单(agent 的 request_refund 调):POST /tickets */
    @PostMapping
    public TicketResponse open(@RequestBody OpenTicketRequest req) {
        return TicketResponse.from(
                service.open(req.orderId(), req.sessionId(), req.userId(), req.reason(), req.itemName()));
    }

    /** 列表(商家台):GET /tickets 或 GET /tickets?status=PENDING */
    @GetMapping
    public List<TicketResponse> list(@RequestParam(required = false) RefundStatus status) {
        return service.list(status).stream().map(TicketResponse::from).toList();
    }

    /** 单条(用户端轮询):GET /tickets/{id} */
    @GetMapping("/{id}")
    public TicketResponse get(@PathVariable Long id) {
        return TicketResponse.from(service.get(id));
    }

    /** 裁决(商家):POST /tickets/{id}/decide  body {"decision":"approve|reject","note":"..."} */
    @PostMapping("/{id}/decide")
    public TicketResponse decide(@PathVariable Long id, @RequestBody DecideRequest req) {
        boolean approve = "approve".equalsIgnoreCase(req.decision());
        return TicketResponse.from(service.decide(id, approve, req.note()));
    }
}
