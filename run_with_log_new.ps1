# 获取当前日期和时间，并格式化为 yyyyMMdd_HHmmss
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# 创建日志目录(如果不存在)
$logDir = "log"
if (!(Test-Path -Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory | Out-Null
}

# 定义日志文件名
$logFile = "$logDir\$timestamp.log"

# 显示执行信息
Write-Host "Executing Python script, the output will be saved to: $logFile"

# 创建不含BOM的批处理文件内容
$batchContent = "@echo off`r`n"
$batchContent += "cd src`r`n"
$batchContent += "chcp 65001 >nul`r`n"
$batchContent += "set PYTHONIOENCODING=utf-8`r`n"
# 关键修改：强制Python无缓冲输出，并确保stdout和stderr同步
$batchContent += "set PYTHONUNBUFFERED=1`r`n"
$batchContent += "python -u main.py > `"..\\$logFile`" 2>&1`r`n"
$batchContent += "exit %errorlevel%`r`n"

# 将批处理命令以ASCII编码保存到临时文件（不含BOM）
$tempBatchFile = [System.IO.Path]::GetTempFileName() + ".bat"
[System.IO.File]::WriteAllText($tempBatchFile, $batchContent, [System.Text.Encoding]::ASCII)

# 执行批处理文件（静默模式，不显示命令输出）
$process = Start-Process -FilePath $tempBatchFile -WindowStyle Hidden -PassThru
$process.WaitForExit()
$exitCode = $process.ExitCode

# 删除临时批处理文件
Remove-Item $tempBatchFile -Force

# 输出执行结果
Write-Host "Python script execution completed, exit code: $exitCode"
Write-Host "OutPut Log file saved to: $logFile"

# 如果需要可以在此打开日志文件
# Invoke-Item $logFile