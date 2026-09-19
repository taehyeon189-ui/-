@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv_ocr\Scripts\python.exe" goto missing
if not exist "app_updater.py" goto missing
if not exist "instance_lock.py" goto missing
echo Close LOOT TRACKER before continuing. Do not delete settings.json.
echo If it cannot close, save your work and restart Windows first.
pause
".venv_ocr\Scripts\python.exe" -c "from pathlib import Path; import app_updater as u; from instance_lock import InstanceLock; root=Path.cwd(); lock=InstanceLock(root/'settings.json'); m=u.check(); raw=u.fetch(u.BASE+m['package']); v,files=u.unpack(raw,m['sha256']); assert v==m['version'], 'Version mismatch'; backup=u.apply_files(root,files); lock.close(); print('Updated to',v,'Backup:',backup)"
if errorlevel 1 goto failed
start "" ".venv_ocr\Scripts\pythonw.exe" launch.py
exit /b 0
:missing
echo Put Repair_Update.bat in the existing LOOT TRACKER folder beside run.bat.
pause
exit /b 1
:failed
echo Update failed. Read the error above. No process was forcibly closed.
echo If LOOT TRACKER is still running, close it or restart Windows and retry.
pause
exit /b 1
