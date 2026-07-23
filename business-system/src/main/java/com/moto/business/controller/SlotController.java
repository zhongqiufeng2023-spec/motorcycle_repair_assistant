package com.moto.business.controller;

import com.moto.business.dto.SlotResponse;
import com.moto.business.service.SlotService;
import org.springframework.web.bind.annotation.*;
import java.util.List;

/** 预约槽位端点。Agent 侧 book_service 来这里查可约。 */
@RestController
@RequestMapping("/slots")
public class SlotController {

    private final SlotService service;

    public SlotController(SlotService service) {
        this.service = service;
    }

    /** GET /slots 或 GET /slots?availableOnly=true —— 列出槽位 */
    @GetMapping
    public List<SlotResponse> list(@RequestParam(defaultValue = "false") boolean availableOnly) {
        return (availableOnly ? service.listAvailable() : service.listAll())
                .stream().map(SlotResponse::from).toList();
    }

    /** GET /slots/{date} —— 单日可约状态;日期不在排班表返回 404 */
    @GetMapping("/{date}")
    public SlotResponse get(@PathVariable String date) {
        return SlotResponse.from(service.get(date));
    }
}
