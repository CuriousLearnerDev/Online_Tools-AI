package main

import (
	"context"
	"fmt"
	"log"
	"path/filepath"
	"sync"
	"time"

	"github.com/zan8in/afrog/v3"
	"github.com/zan8in/afrog/v3/pkg/result"
)

// Async Scan Example / 异步扫描示例
//
// This example demonstrates asynchronous scanning with real-time result streaming.
// It shows how to receive scan results as they are discovered and handle them
// concurrently while the scan is still running.
//
// 此示例演示异步扫描和实时结果流。
// 它展示如何在扫描仍在运行时接收发现的扫描结果，
// 并同时处理它们。

func main() {
	// Create SDK scan options / 创建 SDK 扫描选项
	options := afrog.NewSDKOptions()

	// Set multiple scan targets for better async demonstration
	// 设置多个扫描目标以更好地演示异步功能
	options.Targets = []string{
		"https://www.example.com",
	}

	// Set POC path (required) / 设置 POC 路径（必需）
	pocPath, err := filepath.Abs("../pocs/afrog-pocs")
	if err != nil {
		log.Fatalf("Failed to get POC path / 获取 POC 路径失败: %v", err)
	}
	options.PocFile = pocPath

	// Configuration for async scanning / 异步扫描配置
	options.Concurrency = 8  // Higher concurrency for async / 异步使用更高并发
	options.RateLimit = 30   // Moderate rate limit / 适中的速率限制
	options.Timeout = 12     // Reasonable timeout / 合理的超时时间
	options.Search = "react" // Search fingerprint POCs / 搜索指纹识别 POC
	// options.Severity = "info,low,medium" // Multiple severity levels / 多个严重级别
	options.EnableStream = true // Enable streaming for async results / 启用流式输出获取异步结果

	fmt.Println("Creating SDK scanner for async scanning... / 创建异步扫描的 SDK 扫描器...")

	// Create scanner instance / 创建扫描器实例
	scanner, err := afrog.NewSDKScanner(options)
	if err != nil {
		log.Fatalf("Failed to create scanner / 创建扫描器失败: %v", err)
	}
	defer scanner.Close() // Always close the scanner / 始终关闭扫描器

	// Context for controlling goroutines / 用于控制协程的上下文
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Channels for communication / 用于通信的通道
	resultChan := make(chan *result.Result, 100)
	doneChan := make(chan bool, 1)

	// WaitGroup for synchronization / 用于同步的等待组
	var wg sync.WaitGroup

	// Statistics tracking / 统计跟踪
	var stats struct {
		sync.Mutex
		totalVulns    int
		severityCount map[string]int
		targetVulns   map[string]int
		startTime     time.Time
		lastVulnTime  time.Time
	}
	stats.severityCount = make(map[string]int)
	stats.targetVulns = make(map[string]int)
	stats.startTime = time.Now()

	// Goroutine 1: Real-time result processing / 协程1：实时结果处理
	wg.Add(1)
	go func() {
		defer wg.Done()

		fmt.Println("Starting real-time result processor... / 启动实时结果处理器...")

		for {
			select {
			case result := <-scanner.ResultChan:
				if result == nil {
					fmt.Println("Result channel closed / 结果通道关闭")
					return
				}

				// Process result immediately / 立即处理结果
				processResult(result, &stats)

				// Forward to result channel for other processors / 转发到结果通道供其他处理器使用
				select {
				case resultChan <- result:
				default:
					// Channel full, skip / 通道满了，跳过
				}

			case <-ctx.Done():
				return
			}
		}
	}()

	// Goroutine 2: Progress monitoring / 协程2：进度监控
	wg.Add(1)
	go func() {
		defer wg.Done()

		ticker := time.NewTicker(1 * time.Second)
		defer ticker.Stop()

		fmt.Println("Starting progress monitor... / 启动进度监控器...")

		for {
			select {
			case <-ticker.C:
				progress := scanner.GetProgress()
				scanStats := scanner.GetStats()

				stats.Lock()
				elapsed := time.Since(stats.startTime)
				avgSpeed := float64(scanStats.CompletedScans) / elapsed.Seconds()
				stats.Unlock()

				// Create dynamic progress display / 创建动态进度显示
				fmt.Printf("\r[Progress / 进度] %.1f%% | Completed / 完成: %d/%d | Speed / 速度: %.1f/s | Vulns / 漏洞: %d",
					progress,
					scanStats.CompletedScans,
					scanStats.TotalScans,
					avgSpeed,
					scanStats.FoundVulns)

			case <-ctx.Done():
				return
			case <-doneChan:
				return
			}
		}
	}()

	// Goroutine 3: Result analyzer / 协程3：结果分析器
	wg.Add(1)
	go func() {
		defer wg.Done()

		fmt.Println("Starting result analyzer... / 启动结果分析器...")

		for {
			select {
			case result := <-resultChan:
				if result == nil {
					return
				}

				// Perform detailed analysis / 执行详细分析
				analyzeResult(result)

			case <-ctx.Done():
				return
			}
		}
	}()

	fmt.Println("Starting async scan... / 开始异步扫描...")

	// Start async scan / 开始异步扫描
	err = scanner.RunAsync()
	if err != nil {
		log.Printf("Failed to start async scan / 启动异步扫描失败: %v", err)
		cancel()
		return
	}

	// Simulate some other work while scanning / 在扫描时模拟其他工作
	go func() {
		for i := 0; i < 10; i++ {
			time.Sleep(2 * time.Second)
			fmt.Printf("\n[Background Task / 后台任务] Processing other work... Step %d/10\n", i+1)
		}
	}()

	// Wait for scan completion by monitoring the result channel / 通过监控结果通道等待扫描完成
	go func() {
		// Wait for result channel to close (scan finished)
		// 等待结果通道关闭（扫描完成）
		for range scanner.ResultChan {
			// Channel is still open, scan is running
			// 通道仍然开放，扫描正在运行
		}
		doneChan <- true
	}()

	// Wait for scan completion / 等待扫描完成
	<-doneChan
	fmt.Printf("\n\nScan completed! Cleaning up... / 扫描完成！正在清理...\n")

	// Stop all goroutines / 停止所有协程
	cancel()
	close(resultChan)

	// Wait for all goroutines to finish / 等待所有协程完成
	wg.Wait()

	// Get final results / 获取最终结果
	results := scanner.GetResults()
	finalStats := scanner.GetStats()

	// Print comprehensive results / 打印综合结果
	fmt.Printf("\n========== Async Scan Results / 异步扫描结果 ==========\n")
	fmt.Printf("Total vulnerabilities found / 发现漏洞总数: %d\n", len(results))
	fmt.Printf("Total scans completed / 完成扫描总数: %d\n", finalStats.CompletedScans)
	fmt.Printf("Scan duration / 扫描耗时: %v\n", finalStats.EndTime.Sub(finalStats.StartTime))

	stats.Lock()
	fmt.Printf("Average scan speed / 平均扫描速度: %.2f scans/sec\n",
		float64(finalStats.CompletedScans)/finalStats.EndTime.Sub(finalStats.StartTime).Seconds())

	if len(stats.severityCount) > 0 {
		fmt.Println("\nVulnerability distribution by severity / 按严重程度分布的漏洞:")
		for severity, count := range stats.severityCount {
			fmt.Printf("  %s: %d\n", severity, count)
		}
	}

	if len(stats.targetVulns) > 0 {
		fmt.Println("\nVulnerability distribution by target / 按目标分布的漏洞:")
		for target, count := range stats.targetVulns {
			fmt.Printf("  %s: %d\n", target, count)
		}
	}
	stats.Unlock()

	fmt.Println("\n========== Async Scanning Benefits / 异步扫描的优势 ==========")
	fmt.Println("✓ Real-time result processing / 实时结果处理")
	fmt.Println("✓ Concurrent analysis while scanning / 扫描时并发分析")
	fmt.Println("✓ Non-blocking operation / 非阻塞操作")
	fmt.Println("✓ Better resource utilization / 更好的资源利用")
	fmt.Println("✓ Immediate response to findings / 对发现的立即响应")

	fmt.Println("\nAsync scan completed successfully! / 异步扫描成功完成!")
}

// processResult handles each result as it arrives / 处理每个到达的结果
func processResult(result *result.Result, stats *struct {
	sync.Mutex
	totalVulns    int
	severityCount map[string]int
	targetVulns   map[string]int
	startTime     time.Time
	lastVulnTime  time.Time
}) {
	stats.Lock()
	defer stats.Unlock()

	stats.totalVulns++
	stats.lastVulnTime = time.Now()
	stats.severityCount[result.PocInfo.Info.Severity]++
	stats.targetVulns[result.Target]++

	// Real-time notification / 实时通知
	fmt.Printf("\n🚨 [LIVE] Vulnerability #%d found / 发现漏洞 #%d:\n", stats.totalVulns, stats.totalVulns)
	fmt.Printf("   Target / 目标: %s\n", result.Target)
	fmt.Printf("   POC / POC: %s\n", result.PocInfo.Info.Name)
	fmt.Printf("   Severity / 严重程度: %s\n", result.PocInfo.Info.Severity)
	fmt.Printf("   Time / 时间: %s\n", stats.lastVulnTime.Format("15:04:05"))
}

// analyzeResult performs detailed analysis on each result / 对每个结果执行详细分析
func analyzeResult(result *result.Result) {
	// Simulate some analysis work / 模拟一些分析工作
	time.Sleep(100 * time.Millisecond)

	// Example: Check for specific vulnerability patterns / 示例：检查特定的漏洞模式
	if result.PocInfo.Info.Severity == "high" || result.PocInfo.Info.Severity == "critical" {
		fmt.Printf("\n⚠️  [ALERT] High-priority vulnerability requires immediate attention! / 高优先级漏洞需要立即关注!\n")
		fmt.Printf("   Target / 目标: %s\n", result.Target)
		fmt.Printf("   POC / POC: %s\n", result.PocInfo.Info.Name)

		// Here you could trigger alerts, send notifications, etc.
		// 这里您可以触发警报、发送通知等
	}
}
