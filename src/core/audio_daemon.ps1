# Windows Media Foundation Audio Daemon for Python
# Seamless automatic audio switching between Headphones and Speakers on plug / unplug!

param([string]$initial_file)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    Add-Type -AssemblyName presentationCore
    $player = New-Object System.Windows.Media.MediaPlayer
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}

if ($initial_file) {
    try {
        $player.Open([Uri]$initial_file)
    } catch {}
}

Write-Host "READY"

$running = $true
while ($running) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) {
        break
    }
    $line = $line.Trim()
    if (-not $line) {
        continue
    }

    $parts = $line.Split(" ", 2)
    $cmd = $parts[0].ToUpper()
    $arg = if ($parts.Length -gt 1) { $parts[1] } else { "" }

    switch ($cmd) {
        "OPEN" {
            try {
                $player.Open([Uri]$arg)
                Write-Host "OK"
            } catch {
                Write-Host "ERROR"
            }
        }
        "PLAY" {
            try {
                if ($arg) {
                    $secs = [double]$arg
                    $player.Position = [TimeSpan]::FromSeconds($secs)
                }
                $player.Play()
                Write-Host "OK"
            } catch {
                Write-Host "ERROR"
            }
        }
        "PAUSE" {
            try {
                $player.Pause()
                Write-Host "OK"
            } catch {
                Write-Host "ERROR"
            }
        }
        "STOP" {
            try {
                $player.Stop()
                Write-Host "OK"
            } catch {
                Write-Host "ERROR"
            }
        }
        "SEEK" {
            try {
                if ($arg) {
                    $secs = [double]$arg
                    $player.Position = [TimeSpan]::FromSeconds($secs)
                }
                Write-Host "OK"
            } catch {
                Write-Host "ERROR"
            }
        }
        "VOL" {
            try {
                if ($arg) {
                    $vol = [double]$arg
                    $player.Volume = [Math]::Max(0.0, [Math]::Min(1.0, $vol))
                }
                Write-Host "OK"
            } catch {
                Write-Host "ERROR"
            }
        }
        "QUIT" {
            try {
                $player.Close()
            } catch {}
            $running = $false
            Write-Host "BYE"
        }
    }
}

try {
    $player.Close()
} catch {}
