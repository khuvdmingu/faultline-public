-- Faultline 런처: 앱이 있는 폴더에서 터미널 창 하나를 열어 서버를 띄우고 브라우저를 연다.
-- 끝내려면 그 터미널 창에서 Ctrl+C 또는 창 닫기.
set appPath to POSIX path of (path to me)
set appDir to do shell script "dirname " & quoted form of appPath
tell application "Terminal"
	activate
	do script "cd " & quoted form of appDir & " && sh ./faultline serve --open"
end tell
