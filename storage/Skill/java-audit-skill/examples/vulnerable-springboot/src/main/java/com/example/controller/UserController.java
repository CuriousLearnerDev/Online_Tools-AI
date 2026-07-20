package com.example.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import java.util.List;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private JdbcTemplate jdbcTemplate;

    // VULN-003: SQL 注入
    @GetMapping("/search")
    public List<Object> searchUsers(@RequestParam String keyword) {
        // 危险：SQL 字符串拼接
        String sql = "SELECT * FROM users WHERE name LIKE '%" + keyword + "%'";
        return jdbcTemplate.query(sql, new BeanPropertyRowMapper<>(Object.class));
    }
}