package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.service.OrderService;
import com.example.model.Order;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private OrderService orderService;

    // VULN-004: 水平越权 - 未校验订单归属
    @GetMapping("/{orderId}")
    public Order getOrder(@PathVariable Long orderId) {
        // 危险：未校验订单是否属于当前用户
        return orderService.findById(orderId);
    }
}