package com.example.controller;

import org.springframework.web.bind.annotation.*;
import org.apache.velocity.Template;
import org.apache.velocity.VelocityContext;
import org.apache.velocity.app.VelocityEngine;
import java.io.StringWriter;

@RestController
@RequestMapping("/api/template")
public class TemplateController {

    // VULN-001: Velocity SSTI - 用户输入直接作为模板内容
    @PostMapping("/render")
    public String renderTemplate(@RequestParam String template) {
        VelocityContext context = new VelocityContext();
        StringWriter writer = new StringWriter();
        
        // 危险：用户输入直接作为模板内容，未配置 SecureUberspector
        VelocityEngine engine = new VelocityEngine();
        engine.evaluate(context, writer, "userTemplate", template);
        
        return writer.toString();
    }
}