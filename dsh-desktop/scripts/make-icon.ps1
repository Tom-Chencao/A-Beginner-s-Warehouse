param([string]$OutDir = (Join-Path (Join-Path $PSScriptRoot '..') 'assets'))

Add-Type -AssemblyName System.Drawing

$icoPath  = Join-Path $OutDir 'icon.ico'
$pngPath  = Join-Path $OutDir 'icon.png'
$trayPath = Join-Path $OutDir 'tray.png'

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

# ---- 绘制 256x256 位图 ----
$size = 256
$bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias

$rect = New-Object System.Drawing.Rectangle(0, 0, $size, $size)
$brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, [System.Drawing.Color]::FromArgb(255, 24, 38, 84), [System.Drawing.Color]::FromArgb(255, 66, 99, 235), 55.0)
$g.FillRectangle($brush, $rect)
$brush.Dispose()

$pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(90, 255, 255, 255), 14)
$pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
$g.DrawArc($pen, -60, 130, 320, 260, 200, 110)
$pen.Dispose()

$font = New-Object System.Drawing.Font('Segoe UI', 78, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$sf = New-Object System.Drawing.StringFormat
$sf.Alignment = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center
$txtRect = New-Object System.Drawing.RectangleF(0, 0, $size, $size)
$g.DrawString('DSH', $font, [System.Drawing.Brushes]::White, $txtRect, $sf)
$font.Dispose(); $sf.Dispose()

$borderPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(70, 255, 255, 255), 3)
$g.DrawRectangle($borderPen, 6, 6, $size - 13, $size - 13)
$borderPen.Dispose()
$g.Dispose()

# ---- PNG / tray ----
$bmp.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)

$t = New-Object System.Drawing.Bitmap(32, 32, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g2 = [System.Drawing.Graphics]::FromImage($t)
$g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g2.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g2.DrawImage($bmp, 0, 0, 32, 32)
$g2.Dispose()
$t.Save($trayPath, [System.Drawing.Imaging.ImageFormat]::Png)
$t.Dispose()

# ---- 手工构造标准 ICO（256x256, 32bpp BMP，无 PNG 压缩，兼容性最好）----
$rect = New-Object System.Drawing.Rectangle(0, 0, $size, $size)
$data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$stride = $data.Stride
$bytes = New-Object byte[] ($stride * $size)
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
$bmp.UnlockBits($data)
$bmp.Dispose()

# BGRA 行序翻转（LockBits 是自顶向下，ICO 需要自底向上）
$pixels = New-Object byte[] ($bytes.Length)
for ($y = 0; $y -lt $size; $y++) {
    [Array]::Copy($bytes, $y * $stride, $pixels, ($size - 1 - $y) * $stride, $stride)
}

# ---- 手工构造标准 ICO（256x256, 32bpp BMP，无 PNG 压缩，兼容性最好）----
# 布局: ICONDIR(6) + ICONDIRENTRY(16) + BITMAPINFOHEADER(40) + XOR 像素 + AND 掩码
$maskLen = $size * ($size / 8)
$imgSize = 40 + $pixels.Length + $maskLen
$total = 22 + $imgSize
$buf = New-Object byte[] $total   # 其余字节保持 0（reserved / width / height / biCompression 等均为 0）

[Array]::Copy([BitConverter]::GetBytes([int]1), 0, $buf, 2, 2)    # type: icon
[Array]::Copy([BitConverter]::GetBytes([int]1), 0, $buf, 4, 2)    # count
[Array]::Copy([BitConverter]::GetBytes([int]1), 0, $buf, 10, 2)   # planes
[Array]::Copy([BitConverter]::GetBytes([int]32), 0, $buf, 12, 2)  # bpp
[Array]::Copy([BitConverter]::GetBytes([int]$imgSize), 0, $buf, 14, 4)
[Array]::Copy([BitConverter]::GetBytes([int]22), 0, $buf, 18, 4)  # data offset
[Array]::Copy([BitConverter]::GetBytes([int]40), 0, $buf, 22, 4)  # biSize
[Array]::Copy([BitConverter]::GetBytes([int]$size), 0, $buf, 26, 4)   # biWidth
[Array]::Copy([BitConverter]::GetBytes([int]($size * 2)), 0, $buf, 30, 4)  # biHeight (XOR+AND)
[Array]::Copy([BitConverter]::GetBytes([int]1), 0, $buf, 34, 2)   # biPlanes
[Array]::Copy([BitConverter]::GetBytes([int]32), 0, $buf, 36, 2)  # biBitCount
[Array]::Copy([BitConverter]::GetBytes([int]$pixels.Length), 0, $buf, 44, 4)  # biSizeImage
[Array]::Copy($pixels, 0, $buf, 62, $pixels.Length)               # XOR 像素（自底向上 BGRA）
# AND 掩码保持全 0（全部不透明）

[System.IO.File]::WriteAllBytes($icoPath, $buf)

Write-Host "icons written: $icoPath, $pngPath, $trayPath"
