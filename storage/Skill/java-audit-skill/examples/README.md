# 示例项目

本目录包含示例项目和审计报告，用于参考学习。

---

## 目录结构

```
examples/
├── vulnerable-springboot/     # 存在漏洞的示例项目
│   ├── src/
│   └── audit-report.md        # 完整审计报告示例
│
└── README.md                  # 本文件
```

---

## 使用方法

1. **阅读示例报告**：查看 `vulnerable-springboot/audit-report.md` 了解标准报告格式
2. **对照源码**：查看漏洞对应的源码位置
3. **学习分析方法**：理解调用链追踪、漏洞验证、修复建议的写法

---

## 创建自己的示例

如果发现新的漏洞模式，可以添加到本目录：

```bash
# 1. 创建示例项目目录
mkdir -p examples/your-example/src

# 2. 添加漏洞代码
# 复制存在漏洞的代码到 src/

# 3. 编写审计报告
# 按照 references/report-template.md 格式编写 audit-report.md
```