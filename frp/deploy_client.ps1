# ============================================================
# Windows本地GPU主机部署脚本 (PowerShell)
# ============================================================

Write-Host "========================================" -ForegroundColor Green
Write-Host "部署 frp 客户端到Windows GPU主机" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# 下载frp
$version = "0.52.3"
$downloadUrl = "https://github.com/fatedier/frp/releases/download/v${version}/frp_${version}_windows_amd64.zip"
$output = "$env:TEMP\frp.zip"

Write-Host "正在下载frp..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $downloadUrl -OutFile $output

# 解压
$frpDir = "$env:USERPROFILE\frp"
Expand-Archive -Path $output -DestinationPath $frpDir -Force

Write-Host "========================================" -ForegroundColor Green
Write-Host "frp客户端已下载到: $frpDir" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "接下来请：" -ForegroundColor Yellow
Write-Host "1. 编辑配置文件: $frpDir\frpc.ini" -ForegroundColor Yellow
Write-Host "2. 设置阿里云服务器IP" -ForegroundColor Yellow
Write-Host "3. 设置token（与服务端一致）" -ForegroundColor Yellow
Write-Host "4. 运行: cd $frpDir; .\frpc.exe -c frpc.ini" -ForegroundColor Yellow
Write-Host ""
Write-Host "或者设置为Windows服务（需要管理员权限）：" -ForegroundColor Yellow
Write-Host @"
使用NSSM工具创建服务：
1. 下载 nssm: https://nssm.cc/download
2. 运行: nssm install frpc
3. Path: $frpDir\frpc.exe
4. Startup directory: $frpDir
5. Arguments: -c frpc.ini
6. 点击Install
"@
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
