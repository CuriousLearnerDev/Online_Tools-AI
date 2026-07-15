# Afrog SDK 使用指南

## 概述

Afrog SDK 提供了一个简洁、高效的 Go 编程接口，专为集成漏洞扫描功能而设计。SDK 具有以下核心特性：

### 🚀 核心特性
- ✅ **结构化返回** - 直接返回 Go 结构体，便于程序处理
- ✅ **实时结果流** - 支持同步回调和异步流式输出
- ✅ **OOB 检测支持** - 完整的带外检测配置和管理
- ✅ **详细统计信息** - 提供扫描进度、性能和结果统计
- ✅ **并发安全** - 所有 API 都是线程安全的

## 安装

```bash
go get -u github.com/zan8in/afrog/v3
```

## 快速开始

### 基础扫描示例

最简单的使用方式，适合快速集成：

```go
package main

import (
    "fmt"
    "log"
    "path/filepath"
    "github.com/zan8in/afrog/v3"
)

func main() {
    // 创建扫描选项
    options := afrog.NewSDKOptions()
    
    // 设置扫描目标
    options.Targets = []string{"https://www.example.com"}
    
    // 设置 POC 路径（必须）
    pocPath, _ := filepath.Abs("./pocs/afrog-pocs")
    options.PocFile = pocPath
    
    // 创建扫描器
    scanner, err := afrog.NewSDKScanner(options)
    if err != nil {
        log.Fatal(err)
    }
    defer scanner.Close()
    
    // 执行扫描
    scanner.Run()
    
    // 获取结果
    results := scanner.GetResults()
    fmt.Printf("发现 %d 个漏洞\n", len(results))
}
```

## SDK 配置选项详解

### SDKOptions 结构体

```go
type SDKOptions struct {
    // ========== 目标配置 ==========
    Targets     []string // 扫描目标列表
    TargetsFile string   // 目标文件路径
    
    // ========== POC 配置 ==========
    PocFile  string // POC 文件或目录路径（必须）
    Search   string // POC 搜索关键词
    Severity string // 严重程度过滤
    
    // ========== 性能配置 ==========
    RateLimit    int // 请求速率限制 (默认: 150)
    Concurrency  int // 并发数 (默认: 25)
    Retries      int // 重试次数 (默认: 1)
    Timeout      int // 超时时间秒 (默认: 10)
    MaxHostError int // 主机最大错误数 (默认: 3)

    // ========== PortScan 预扫描配置 ==========
    PortScan        bool   // 启用端口预扫描（等价于 CLI 的 -ps）
    PSPorts         string // 预扫描端口定义：top/full/all/80,443/1-1024 等（等价于 -p）
    PSRateLimit     int    // 预扫描速率限制（等价于 -prate）
    PSTimeout       int    // 预扫描超时（毫秒，等价于 -ptimeout）
    PSRetries       int    // 预扫描重试（等价于 -ptries）
    PSSkipDiscovery bool   // 跳过存活探测（等价于 -Pn）
    PSS4Chunk       int    // 全端口扫描 chunk（等价于 --ps-s4-chunk）
    
    // ========== 网络配置 ==========
    Proxy string // HTTP/SOCKS5 代理
    
    // ========== OOB 配置 ==========
    EnableOOB  bool   // 是否启用 OOB 检测
    OOB        string // OOB 适配器类型
    OOBKey     string // OOB API 密钥
    OOBDomain  string // OOB 域名
    OOBApiUrl  string // OOB API 地址
    OOBHttpUrl string // OOB HTTP 地址
    
    // ========== 输出配置 ==========
    EnableStream bool // 启用流式输出
}
```

### 配置选项说明

#### 目标配置
- `Targets`: 直接指定扫描目标列表
- `TargetsFile`: 从文件读取目标列表（每行一个）

#### POC 配置
- `PocFile`: **必须**指定 POC 文件或目录路径
- `Search`: 按关键词过滤 POC，如 "tomcat,phpinfo"
- `Severity`: 按严重程度过滤，如 "high,critical"

#### 性能调优
- `Concurrency`: 并发扫描线程数，建议根据目标数量调整
- `RateLimit`: 每秒请求数限制，避免触发防护
- `Timeout`: 单个请求超时时间
- `Retries`: 失败重试次数

## 核心功能示例

### 1. 实时结果回调

在发现漏洞时立即处理：

```go
scanner.OnResult = func(r *result.Result) {
    fmt.Printf("发现漏洞: %s - %s [%s]\n", 
        r.Target, 
        r.PocInfo.Info.Name,
        r.PocInfo.Info.Severity)
    
    // 立即处理逻辑
    if r.PocInfo.Info.Severity == "critical" {
        sendAlert(r)
    }
}

scanner.Run()
```

### 2. 进度监控

实时监控扫描进度：

```go
go func() {
    ticker := time.NewTicker(1 * time.Second)
    defer ticker.Stop()
    
    for range ticker.C {
        progress := scanner.GetProgress()
        stats := scanner.GetStats()
        fmt.Printf("进度: %.2f%% (%d/%d) 发现漏洞: %d\n", 
            progress, 
            stats.CompletedScans,
            stats.TotalScans,
            stats.FoundVulns)
    }
}()

scanner.Run()
```

### 3. 异步扫描与流式输出

非阻塞扫描，实时获取结果：

```go
options.EnableStream = true
scanner, _ := afrog.NewSDKScanner(options)

// 启动异步扫描
scanner.RunAsync()

// 从通道读取实时结果
for result := range scanner.ResultChan {
    fmt.Printf("实时发现: %s - %s\n", 
        result.Target, 
        result.PocInfo.Info.Name)
    
    // 实时处理每个结果
    processResult(result)
}
```

### 4. OOB（带外）检测配置

#### CEYE.io 配置（推荐）
```go
options.EnableOOB = true
options.OOB = "ceyeio"
options.OOBKey = "your-ceye-api-token"
options.OOBDomain = "your-subdomain.ceye.io"
```

#### DNSLog.cn 配置（免费）
```go
options.EnableOOB = true
options.OOB = "dnslogcn"
options.OOBDomain = "your.dnslog.cn"
```

#### 其他 OOB 服务
```go
// Alphalog
options.OOB = "alphalog"
options.OOBDomain = "your.alphalog.cn"
options.OOBApiUrl = "https://api.alphalog.cn"

// XRay
options.OOB = "xray"
options.OOBDomain = "your.xray.domain"
options.OOBApiUrl = "http://xray-api:8777"
options.OOBKey = "your-xray-token"
```

#### OOB 状态检查
```go
if oobEnabled, oobStatus := scanner.GetOOBStatus(); oobEnabled {
    fmt.Printf("✓ OOB 状态: %s\n", oobStatus)
} else {
    fmt.Printf("✗ OOB 状态: %s\n", oobStatus)
}
```

### 5. 端口预扫描（PortScan）

SDK 支持在 PoC 扫描之前做一次端口预扫描：扫描到的开放端口会自动追加进内部 Targets（以 `host:port` 形式），后续 PoC 会按新的目标集合执行。

SDK 模式下不会默认把开放端口输出到控制台，可以通过回调或获取结果来消费。

```go
options := afrog.NewSDKOptions()
options.Targets = []string{"1.2.3.4"}
options.PocFile = pocPath

options.PortScan = true
options.PSPorts = "top" // 或 "full"/"all"/"80,443"/"1-1024"
options.PSSkipDiscovery = true
options.PSTimeout = 500

scanner, _ := afrog.NewSDKScanner(options)

scanner.OnPort = func(host string, port int) {
    fmt.Printf("open: %s:%d\n", host, port)
}

scanner.Run()

open := scanner.GetOpenPorts()
_ = open
```

也可以通过 `PortChan` 异步消费端口预扫描结果：启用 `PortScan` 时会自动初始化该通道，扫描结束后会自动关闭。

```go
options := afrog.NewSDKOptions()
options.Targets = []string{"1.2.3.4"}
options.PocFile = pocPath
options.PortScan = true

scanner, _ := afrog.NewSDKScanner(options)

_ = scanner.RunAsync()

for r := range scanner.PortChan {
    fmt.Printf("open: %s:%d\n", r.Host, r.Port)
}
```

也可以直接运行示例：`examples/sdk_portscan/`。

## API 方法参考

### SDKScanner 核心方法

| 方法 | 描述 | 返回值 |
|-----|-----|-------|
| `NewSDKScanner(opts)` | 创建扫描器实例 | `*SDKScanner, error` |
| `Run()` | 同步执行扫描 | `error` |
| `RunAsync()` | 异步执行扫描 | `error` |
| `GetResults()` | 获取所有扫描结果 | `[]*result.Result` |
| `GetOpenPorts()` | 获取预扫描开放端口 | `map[string][]int` |
| `GetStats()` | 获取扫描统计信息 | `ScanStats` |
| `GetProgress()` | 获取扫描进度(0-100) | `float64` |
| `GetVulnerabilityCount()` | 获取漏洞数量 | `int` |
| `HasVulnerabilities()` | 检查是否有漏洞 | `bool` |
| `Stop()` | 停止扫描 | - |
| `Close()` | 关闭扫描器，释放资源 | - |

### 动态配置方法

| 方法 | 描述 |
|-----|-----|
| `SetProxy(proxy)` | 动态设置代理 |
| `SetRateLimit(n)` | 动态设置速率限制 |
| `SetConcurrency(n)` | 动态设置并发数 |

### OOB 相关方法

| 方法 | 描述 | 返回值 |
|-----|-----|-------|
| `IsOOBEnabled()` | 检查是否启用 OOB | `bool` |
| `GetOOBStatus()` | 获取 OOB 状态信息 | `bool, string` |

### ScanStats 统计结构

```go
type ScanStats struct {
    StartTime      time.Time  // 扫描开始时间
    EndTime        time.Time  // 扫描结束时间
    TotalTargets   int        // 总目标数
    TotalPocs      int        // 总 POC 数
    TotalScans     int        // 总扫描任务数
    CompletedScans int32      // 已完成扫描数
    FoundVulns     int32      // 发现的漏洞数
}
```

## 高级用法示例

### 批量扫描与结果分析

```go
options := afrog.NewSDKOptions()
options.TargetsFile = "targets.txt"  // 从文件读取大量目标
options.PocFile = "/path/to/pocs"
options.Severity = "high,critical"   // 只扫描高危漏洞
options.Concurrency = 50            // 提高并发数

scanner, _ := afrog.NewSDKScanner(options)

// 分类处理不同严重程度的漏洞
scanner.OnResult = func(r *result.Result) {
    switch r.PocInfo.Info.Severity {
    case "critical":
        sendUrgentAlert(r)
    case "high":
        logHighRiskVuln(r)
    default:
        saveToDatabase(r)
    }
}

scanner.Run()
results := scanner.GetResults()
generateReport(results)
```

### 智能扫描控制

```go
scanner.OnResult = func(r *result.Result) {
    // 发现严重漏洞时停止扫描
    if r.PocInfo.Info.Severity == "critical" {
        fmt.Println("发现严重漏洞，停止扫描")
        scanner.Stop()
    }
}

// 动态调整扫描参数
go func() {
    time.Sleep(30 * time.Second)
    // 30秒后降低速率
    scanner.SetRateLimit(50)
}()
```

### 多目标并行扫描

```go
targets := [][]string{
    {"https://site1.com", "https://site2.com"},
    {"https://site3.com", "https://site4.com"},
}

var wg sync.WaitGroup
results := make(chan []*result.Result, len(targets))

for _, targetGroup := range targets {
    wg.Add(1)
    go func(targets []string) {
        defer wg.Done()
        
        options := afrog.NewSDKOptions()
        options.Targets = targets
        options.PocFile = pocPath
        
        scanner, _ := afrog.NewSDKScanner(options)
        defer scanner.Close()
        
        scanner.Run()
        results <- scanner.GetResults()
    }(targetGroup)
}

wg.Wait()
close(results)

// 汇总所有结果
allResults := []*result.Result{}
for groupResults := range results {
    allResults = append(allResults, groupResults...)
}
```

## 性能优化建议

### 1. 并发数优化

```go
targetCount := len(options.Targets)

// 根据目标数量动态调整并发数
switch {
case targetCount <= 10:
    options.Concurrency = 5
case targetCount <= 100:
    options.Concurrency = 25
case targetCount <= 1000:
    options.Concurrency = 50
default:
    options.Concurrency = 100
}
```

### 2. 内存优化

```go
// 对于大规模扫描，使用流式输出避免内存积累
options.EnableStream = true

// 及时处理结果，不要积累
scanner.OnResult = func(r *result.Result) {
    processImmediately(r)
    // 不要存储到切片中
}
```

### 3. 网络优化

```go
// 网络不稳定时的配置
options.Retries = 3
options.Timeout = 30
options.RateLimit = 50  // 降低请求频率

// 使用代理池
proxies := []string{"proxy1:8080", "proxy2:8080"}
scanner.SetProxy(proxies[rand.Intn(len(proxies))])
```

## 错误处理最佳实践

### 完整的错误处理

```go
scanner, err := afrog.NewSDKScanner(options)
if err != nil {
    switch {
    case strings.Contains(err.Error(), "POC文件"):
        log.Fatal("POC 配置错误:", err)
    case strings.Contains(err.Error(), "目标"):
        log.Fatal("目标配置错误:", err)
    default:
        log.Fatal("初始化失败:", err)
    }
}

// 扫描错误处理
if err := scanner.Run(); err != nil {
    log.Printf("扫描异常: %v", err)
    
    // 即使出错也可以获取部分结果
    results := scanner.GetResults()
    if len(results) > 0 {
        fmt.Printf("获得部分结果: %d 个漏洞\n", len(results))
    }
}
```

### 超时和取消处理

```go
ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
defer cancel()

go func() {
    scanner.RunAsync()
}()

select {
case <-ctx.Done():
    scanner.Stop()
    fmt.Println("扫描超时，已停止")
case <-scanner.ResultChan:
    // 正常完成
}
```

## 集成示例

### Web 服务集成

```go
func scanHandler(w http.ResponseWriter, r *http.Request) {
    target := r.URL.Query().Get("target")
    
    options := afrog.NewSDKOptions()
    options.Targets = []string{target}
    options.PocFile = os.Getenv("POC_PATH")
    
    scanner, err := afrog.NewSDKScanner(options)
    if err != nil {
        http.Error(w, err.Error(), 500)
        return
    }
    defer scanner.Close()
    
    scanner.Run()
    results := scanner.GetResults()
    
    // 返回 JSON 结果
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]interface{}{
        "vulnerabilities": len(results),
        "results": results,
    })
}
```

### CI/CD 集成

```go
func main() {
    options := afrog.NewSDKOptions()
    options.TargetsFile = "staging-urls.txt"
    options.PocFile = "/security/pocs"
    options.Severity = "high,critical"
    
    scanner, err := afrog.NewSDKScanner(options)
    if err != nil {
        os.Exit(1)
    }
    defer scanner.Close()
    
    scanner.Run()
    
    if scanner.HasVulnerabilities() {
        fmt.Println("❌ 发现安全漏洞，阻止部署")
        results := scanner.GetResults()
        for _, r := range results {
            fmt.Printf("- %s: %s\n", r.Target, r.PocInfo.Info.Name)
        }
        os.Exit(1)
    }
    
    fmt.Println("✅ 安全检查通过")
}
```

## 常见问题解答

### Q: 如何让弱口令/默认口令 PoC 仅在命中指纹后执行？
A: 在 PoC 的 `info` 中使用 `requires` 与 `requires-mode` 声明指纹依赖，并使用 `requires-mode: strict` 实现“先指纹后执行”。完整用法与排障请参考：[requires 指纹门控：用法教程与问题答疑](requires-gating-guide.md)

### Q: 如何处理大量目标的扫描？
A: 使用流式输出和适当的并发控制：
```go
options.EnableStream = true
options.Concurrency = 50
scanner.OnResult = func(r *result.Result) {
    // 立即处理，不要积累
    processImmediately(r)
}
```

### Q: 如何确保 OOB 检测正常工作？
A: 在扫描前检查 OOB 状态：
```go
if enabled, status := scanner.GetOOBStatus(); !enabled {
    log.Printf("OOB 警告: %s", status)
}
```

### Q: 如何优化扫描性能？
A: 根据网络和目标情况调整参数：
```go
// 内网扫描
options.Concurrency = 100
options.RateLimit = 500

// 外网扫描
options.Concurrency = 25
options.RateLimit = 150
options.Timeout = 15
```

### Q: 如何处理扫描中断？
A: 使用 context 和信号处理：
```go
c := make(chan os.Signal, 1)
signal.Notify(c, os.Interrupt)

go func() {
    <-c
    scanner.Stop()
    fmt.Println("扫描已停止")
}()
```

## 注意事项

1. **POC 路径必须指定** - SDK 不会自动下载或查找 POC
2. **完全静默运行** - 不会有控制台输出，适合程序集成
3. **无文件生成** - 不会创建任何报告文件
4. **资源管理** - 必须调用 `Close()` 释放资源
5. **并发安全** - 所有方法都是并发安全的
6. **OOB 配置** - 需要正确配置才能检测带外漏洞

## 许可证

MIT License

---

更多示例和详细文档，请参考 `examples/` 目录中的示例代码。
