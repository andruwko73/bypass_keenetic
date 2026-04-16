param(
    [string]$Branch = 'main'
)

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot

Write-Host "Fetching origin..."
git fetch origin

Write-Host "Checking out $Branch..."
git checkout $Branch

Write-Host "Merging origin/$Branch..."
git merge --ff-only "origin/$Branch"

Write-Host "Pushing $Branch to userfork..."
git push userfork $Branch

Write-Host "Update complete: userfork/$Branch is now synced with origin/$Branch."