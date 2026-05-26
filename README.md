# TaskbarHider

Windows 작업표시줄에서 실행 중인 앱 버튼을 숨기는 도구.

## 원리

Windows 창의 확장 스타일(`Extended Window Style`)을 변경합니다.

- `WS_EX_APPWINDOW` 제거 → 작업표시줄 표시 조건 해제
- `WS_EX_TOOLWINDOW` 추가 → 작업표시줄에서 완전히 제거

**앱은 계속 실행 중**이며, Alt+Tab 또는 직접 클릭으로 접근할 수 있습니다.

## 설치 및 실행

```powershell
# 1. Python 3.8+ 필요 (의존성 없음, 표준 라이브러리만 사용)
python taskbar_hider.py
```

## .exe로 만들기

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name TaskbarHider taskbar_hider.py
# → dist/TaskbarHider.exe 생성
```

## 사용법

1. 프로그램 실행 → GUI 창이 열림
2. 상단 목록: 현재 작업표시줄에 표시 중인 창
3. **Hide from Taskbar** → 선택한 창이 작업표시줄에서 사라짐
4. 하단 목록: 숨겨진 창
5. **Show on Taskbar** → 선택한 창이 다시 작업표시줄에 나타남
6. **Restore All & Quit** → 모든 창 복원 후 종료

## 주의사항

- 프로그램 종료 시 자동으로 모든 숨긴 창이 복원됩니다.
- 관리자 권한으로 실행된 앱을 숨기려면 이 프로그램도 관리자 권한으로 실행해야 합니다.
- UWP 앱(Microsoft Store 앱)은 일부 제한이 있을 수 있습니다.
