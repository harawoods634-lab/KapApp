@echo off
cd /d "C:\Users\JimElf\kap-app"
docker-compose up -d
timeout /t 5
start http://localhost:8501
exit