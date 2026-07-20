package com.example.util;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.parser.ParserConfig;

public class JsonUtil {

    // VULN-002: Fastjson 反序列化 RCE
    public static Object parse(String json) {
        // 危险：未开启 safeMode，Fastjson 1.2.47 存在已知漏洞
        return JSON.parse(json);
    }
    
    public static String toJson(Object obj) {
        return JSON.toJSONString(obj);
    }
}