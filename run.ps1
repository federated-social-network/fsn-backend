# PowerShell Script for FSN Backend
# Usage: .\run.ps1 [command]

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

function Show-Help {
    Write-Host "Available commands:" -ForegroundColor Cyan
    Write-Host "  .\run.ps1 install         - Install production dependencies"
    Write-Host "  .\run.ps1 dev            - Install development dependencies"
    Write-Host "  .\run.ps1 run            - Run the development server"
    Write-Host "  .\run.ps1 test           - Run tests with pytest"
    Write-Host "  .\run.ps1 clean          - Remove Python cache files"
    Write-Host "  .\run.ps1 migrate        - Create database tables"
    Write-Host "  .\run.ps1 docker-build   - Build Docker image"
    Write-Host "  .\run.ps1 docker-run     - Run Docker container"
    Write-Host "  .\run.ps1 lint           - Run code linting"
    Write-Host "  .\run.ps1 format         - Format code with black"
    Write-Host "  .\run.ps1 create-token   - Create Gmail OAuth refresh token"
    Write-Host "  .\run.ps1 run-instance-a - Run Instance A (port 8000)"
    Write-Host "  .\run.ps1 run-instance-b - Run Instance B (port 8001)"
}

function Install-Dependencies {
    Write-Host "Installing production dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
}

function Install-DevDependencies {
    Write-Host "Installing development dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
    pip install black flake8 isort pytest-cov
}

function Start-Server {
    Write-Host "Starting development server..." -ForegroundColor Green
    & "C:\Program Files\Python310\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}

function Run-Tests {
    Write-Host "Running tests..." -ForegroundColor Green
    pytest -v
}

function Clean-Cache {
    Write-Host "Cleaning Python cache files..." -ForegroundColor Green
    Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Get-ChildItem -Path . -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force
    Get-ChildItem -Path . -Recurse -Directory -Filter "*.egg-info" | Remove-Item -Recurse -Force
    Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force
    if (Test-Path "htmlcov") { Remove-Item -Path "htmlcov" -Recurse -Force }
    if (Test-Path ".coverage") { Remove-Item -Path ".coverage" -Force }
    Write-Host "Cleanup complete!" -ForegroundColor Green
}

function Run-Migration {
    Write-Host "Creating database tables..." -ForegroundColor Green
    python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine); print('Database tables created successfully')"
}

function Build-Docker {
    Write-Host "Building Docker image..." -ForegroundColor Green
    docker build -t fsn-backend .
}

function Run-Docker {
    Write-Host "Running Docker container..." -ForegroundColor Green
    docker run -p 8080:8080 --env-file .env fsn-backend
}

function Run-Lint {
    Write-Host "Running linting..." -ForegroundColor Green
    flake8 app/ tests/ --max-line-length=120 --exclude=__pycache__
}

function Format-Code {
    Write-Host "Formatting code..." -ForegroundColor Green
    black app/ tests/ --line-length=120
    isort app/ tests/
}

function Create-Token {
    Write-Host "Creating Gmail OAuth refresh token..." -ForegroundColor Green
    python create_refresh_token.py
}

function Run-InstanceA {
    Write-Host "Starting Instance A on port 8000..." -ForegroundColor Green
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env.InstanceA
}

function Run-InstanceB {
    Write-Host "Starting Instance B on port 8001..." -ForegroundColor Green
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 --env-file .env.InstanceB
}

# Command dispatcher
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "install" { Install-Dependencies }
    "dev" { Install-DevDependencies }
    "run" { Start-Server }
    "test" { Run-Tests }
    "clean" { Clean-Cache }
    "migrate" { Run-Migration }
    "docker-build" { Build-Docker }
    "docker-run" { Run-Docker }
    "lint" { Run-Lint }
    "format" { Format-Code }
    "create-token" { Create-Token }
    "run-instance-a" { Run-InstanceA }
    "run-instance-b" { Run-InstanceB }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
    }
}