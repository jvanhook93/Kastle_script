# Navigate to your backend folder (adjust if needed)
cd "C:\Users\javan\Kastle_script\backend"

# Kill any process using port 5000
Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction Stop
        Write-Host "Killed process $($_.OwningProcess) using port 5000"
    } catch {
        Write-Host "Process $($_.OwningProcess) not found, skipping."
    }
}

# Start Flask
Write-Host "Starting Flask backend..."
python app.py
