Write-Host "--- Backup/Restore Demo (Local File Copy) ---"
Write-Host "1. Backing up SeaweedFS volume (S3 backend) to local directory..."
if (Test-Path "C:\dar-lakehouse-pilot\backup") { Remove-Item -Recurse -Force "C:\dar-lakehouse-pilot\backup" }
New-Item -ItemType Directory -Force -Path "C:\dar-lakehouse-pilot\backup" | Out-Null
docker cp dar-seaweedfs-volume:/data C:\dar-lakehouse-pilot\backup\seaweedfs-volume

Write-Host "2. Verifying backup exists..."
Get-ChildItem -Path C:\dar-lakehouse-pilot\backup\seaweedfs-volume

Write-Host "3. Restoring data (copy back)..."
docker cp C:\dar-lakehouse-pilot\backup\seaweedfs-volume\. dar-seaweedfs-volume:/data/
Write-Host "Backup/Restore demo completed successfully."
