# Audit all locked dependencies for known vulnerabilities (blueprint §14.3).
# Usage (from the project folder):   powershell -ExecutionPolicy Bypass -File scripts\audit.ps1
# Exit code 0 = no known vulnerabilities.

$req = Join-Path $env:TEMP "ats-requirements-audit.txt"
uv export --format requirements-txt --frozen --no-emit-project -q | Out-File -Encoding ascii $req
uv run pip-audit -r $req --require-hashes --disable-pip
$code = $LASTEXITCODE
Remove-Item $req -ErrorAction SilentlyContinue
exit $code
