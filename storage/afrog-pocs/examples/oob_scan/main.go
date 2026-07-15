package main

import (
	"fmt"
	"log"
	"path/filepath"
	"strings"

	"github.com/zan8in/afrog/v3"
	"github.com/zan8in/afrog/v3/pkg/poc"
	"github.com/zan8in/afrog/v3/pkg/result"
)

// OOB (Out-of-Band) Scan Example / OOB（带外）扫描示例
//
// This example demonstrates how to configure and use OOB detection
// with different OOB adapters like ceyeio, dnslogcn, alphalog, etc.
//
// 此示例演示如何配置和使用 OOB 检测，
// 支持不同的 OOB 适配器，如 ceyeio、dnslogcn、alphalog 等。

func main() {
	// Create SDK scan options / 创建 SDK 扫描选项
	options := afrog.NewSDKOptions()

	// Set scan targets / 设置扫描目标
	options.Targets = []string{
		"https://www.example.com",
	}

	// Set POC path (required) / 设置 POC 路径（必需）
	pocPath, err := filepath.Abs("../pocs/afrog-pocs")
	if err != nil {
		log.Fatalf("Failed to get POC path / 获取 POC 路径失败: %v", err)
	}
	options.PocFile = pocPath

	// Basic configuration / 基础配置
	options.Concurrency = 10
	options.RateLimit = 50
	options.Timeout = 15
	options.Severity = "info,low,medium,high,critical" // All severity levels / 所有严重级别

	// ========== OOB Configuration / OOB 配置 ==========
	// Enable OOB detection / 启用 OOB 检测
	options.EnableOOB = true

	// Method 1: Configure CEYE.io (recommended) / 方法1：配置 CEYE.io（推荐）
	// Register at http://ceye.io/ to get your token and domain
	// 在 http://ceye.io/ 注册以获取您的令牌和域名
	options.OOB = "ceyeio"
	options.OOBKey = "your-ceye-api-token"       // Replace with your CEYE API token / 替换为您的 CEYE API 令牌
	options.OOBDomain = "your-subdomain.ceye.io" // Replace with your CEYE domain / 替换为您的 CEYE 域名

	// Method 2: Configure DNSLog.cn (free, no registration required)
	// 方法2：配置 DNSLog.cn（免费，无需注册）
	// Uncomment the following lines to use DNSLog.cn instead:
	// 取消注释以下行以使用 DNSLog.cn：
	// options.OOB = "dnslogcn"
	// options.OOBDomain = "your.dnslog.cn" // Get from http://dnslog.cn/

	// Method 3: Configure Alphalog
	// 方法3：配置 Alphalog
	// options.OOB = "alphalog"
	// options.OOBDomain = "your.alphalog.cn"
	// options.OOBApiUrl = "https://api.alphalog.cn"

	// Method 4: Configure XRay
	// 方法4：配置 XRay
	// options.OOB = "xray"
	// options.OOBDomain = "your.xray.domain"
	// options.OOBApiUrl = "http://xray-api:8777"
	// options.OOBKey = "your-xray-token"

	// Method 5: Configure RevSuit
	// 方法5：配置 RevSuit
	// options.OOB = "revsuit"
	// options.OOBKey = "your-revsuit-key"
	// options.OOBDomain = "your.revsuit.domain"
	// options.OOBHttpUrl = "http://your.revsuit.domain"
	// options.OOBApiUrl = "http://your.revsuit.domain:8080"

	fmt.Println("Creating SDK scanner with OOB configuration... / 创建带 OOB 配置的 SDK 扫描器...")

	// Create scanner instance / 创建扫描器实例
	scanner, err := afrog.NewSDKScanner(options)
	if err != nil {
		log.Fatalf("Failed to create scanner / 创建扫描器失败: %v", err)
	}
	defer scanner.Close() // Always close the scanner / 始终关闭扫描器

	// Check OOB status before scanning / 扫描前检查 OOB 状态
	if oobEnabled, oobStatus := scanner.GetOOBStatus(); oobEnabled {
		fmt.Printf("✓ OOB Status / OOB 状态: %s\n", oobStatus)
	} else {
		fmt.Printf("✗ OOB Status / OOB 状态: %s\n", oobStatus)
		fmt.Println("Warning: OOB is not properly configured. Some POCs may not work correctly.")
		fmt.Println("警告：OOB 未正确配置。某些 POC 可能无法正常工作。")

		// You can choose to continue without OOB or exit
		// 您可以选择在没有 OOB 的情况下继续或退出
		// return
	}

	// Set up real-time result callback / 设置实时结果回调
	var oobVulnCount, normalVulnCount int
	scanner.OnResult = func(r *result.Result) {
		// Check if this is an OOB-related vulnerability / 检查是否为 OOB 相关漏洞
		isOOBVuln := r.PocInfo != nil && pocUsesOOB(r.PocInfo)

		if isOOBVuln {
			oobVulnCount++
			fmt.Printf("\n[OOB Vulnerability Found / 发现 OOB 漏洞] 🚨\n")
		} else {
			normalVulnCount++
			fmt.Printf("\n[Standard Vulnerability Found / 发现标准漏洞] ⚠️\n")
		}

		fmt.Printf("  Target / 目标: %s\n", r.Target)
		fmt.Printf("  POC Name / POC 名称: %s\n", r.PocInfo.Info.Name)
		fmt.Printf("  Severity / 严重程度: %s\n", r.PocInfo.Info.Severity)
		fmt.Printf("  Author / 作者: %s\n", r.PocInfo.Info.Author)
		if r.PocInfo.Info.Description != "" {
			fmt.Printf("  Description / 描述: %s\n", r.PocInfo.Info.Description)
		}
		fmt.Println("  " + strings.Repeat("-", 50))
	}

	fmt.Println("Starting OOB-enabled scan... / 开始启用 OOB 的扫描...")

	// Execute scan (synchronous) / 执行扫描（同步）
	err = scanner.Run()
	if err != nil {
		log.Printf("Scan error occurred / 扫描出现错误: %v", err)
	}

	// Get scan results / 获取扫描结果
	results := scanner.GetResults()
	stats := scanner.GetStats()

	// Print comprehensive results / 打印综合结果
	fmt.Printf("\n========== OOB Scan Results / OOB 扫描结果 ==========\n")
	fmt.Printf("Total vulnerabilities found / 发现漏洞总数: %d\n", len(results))
	fmt.Printf("  - OOB vulnerabilities / OOB 漏洞: %d\n", oobVulnCount)
	fmt.Printf("  - Standard vulnerabilities / 标准漏洞: %d\n", normalVulnCount)
	fmt.Printf("Scan progress / 扫描进度: %.1f%%\n", scanner.GetProgress())
	fmt.Printf("Scan duration / 扫描耗时: %v\n", stats.EndTime.Sub(stats.StartTime))

	// Analyze POC types used / 分析使用的 POC 类型
	if len(results) > 0 {
		fmt.Printf("\n========== Vulnerability Analysis / 漏洞分析 ==========\n")

		severityCount := make(map[string]int)
		pocTypeCount := make(map[string]int)

		for _, result := range results {
			severityCount[result.PocInfo.Info.Severity]++

			// Analyze POC type / 分析 POC 类型
			isOOB := false
			for _, rule := range result.PocInfo.Set {
				if key, ok := rule.Key.(string); ok && (key == "oob" || key == "reverse") {
					isOOB = true
					break
				}
			}

			if isOOB {
				pocTypeCount["OOB"]++
			} else {
				pocTypeCount["Standard"]++
			}
		}

		fmt.Println("By Severity / 按严重程度:")
		for severity, count := range severityCount {
			fmt.Printf("  %s: %d\n", severity, count)
		}

		fmt.Println("\nBy POC Type / 按 POC 类型:")
		for pocType, count := range pocTypeCount {
			fmt.Printf("  %s: %d\n", pocType, count)
		}
	} else {
		fmt.Println("No vulnerabilities found / 未发现漏洞")
		fmt.Println("This might be because:")
		fmt.Println("这可能是因为:")
		fmt.Println("1. The targets are secure / 目标是安全的")
		fmt.Println("2. OOB configuration is incorrect / OOB 配置不正确")
		fmt.Println("3. Network connectivity issues / 网络连接问题")
	}

	fmt.Println("\n========== OOB Configuration Tips / OOB 配置提示 ==========")
	fmt.Println("For best results with OOB detection:")
	fmt.Println("为了获得 OOB 检测的最佳结果:")
	fmt.Println("1. Use CEYE.io for most reliable results / 使用 CEYE.io 获得最可靠的结果")
	fmt.Println("2. Ensure your OOB service is accessible / 确保您的 OOB 服务可访问")
	fmt.Println("3. Check firewall settings / 检查防火墙设置")
	fmt.Println("4. Verify API tokens and domains / 验证 API 令牌和域名")

	fmt.Println("\nOOB scan completed! / OOB 扫描完成!")
}

func pocUsesOOB(p *poc.Poc) bool {
	if p == nil {
		return false
	}
	if containsOOBToken(p.Expression) {
		return true
	}
	for _, it := range p.Set {
		if s, ok := it.Value.(string); ok && containsOOBToken(s) {
			return true
		}
	}
	for _, rm := range p.Rules {
		r := rm.Value
		if containsOOBToken(r.Expression) {
			return true
		}
		for _, e := range r.Expressions {
			if containsOOBToken(e) {
				return true
			}
		}
		req := r.Request
		if containsOOBToken(req.Path) || containsOOBToken(req.Host) || containsOOBToken(req.Body) || containsOOBToken(req.Raw) || containsOOBToken(req.Data) {
			return true
		}
		for _, hv := range req.Headers {
			if containsOOBToken(hv) {
				return true
			}
		}
	}
	return false
}

func containsOOBToken(s string) bool {
	if s == "" {
		return false
	}
	l := strings.ToLower(s)
	return strings.Contains(l, "oobwait(") ||
		strings.Contains(l, "{{oob") ||
		strings.Contains(l, "{{ oob") ||
		strings.Contains(l, "oob_") ||
		strings.Contains(l, "oob.")
}
