# FolderPopup

바탕화면의 폴더를 열면 탐색기 창 대신, 삼성 폰 폴더처럼 **아이콘 + 이름이 담긴 팝업**이 뜨게 해주는 Windows용 프로그램입니다.

## 사용 방법

### 1. 실행 파일 받기
- GitHub 저장소의 **Releases**에서 `FolderPopup.exe`를 받거나,
- **Actions → Build exe → Run workflow** 로 직접 빌드한 뒤 Artifacts에서 받습니다.

### 2. 폴더 정리
팝업으로 쓸 폴더(예: `게임`)를 바탕화면이 아닌 다른 위치로 옮겨 둡니다.
예: `D:\Folders\게임`  (안에는 지금처럼 바로가기를 넣어 두면 됩니다)

### 3. 바탕화면 바로가기 만들기
명령 프롬프트(또는 PowerShell)에서:

```
FolderPopup.exe "D:\Folders\게임" --install
```

바탕화면에 `게임` 바로가기가 생기고, 더블클릭하면 팝업이 열립니다.

## 옵션

| 옵션 | 설명 |
|------|------|
| `--install` | 바탕화면에 팝업용 바로가기 생성 |
| `--at-cursor` | 화면 중앙 대신 마우스 근처에서 열기 (`--install`과 함께 쓰면 바로가기에도 적용) |
| `--columns N` | 한 줄에 보여줄 아이콘 수 (기본 4) |

## 조작
- 아이콘 클릭: 해당 프로그램/파일 실행 후 팝업 닫힘
- 팝업 바깥 클릭 또는 `Esc`: 닫기
- 하단 "탐색기에서 열기": 원래 폴더 창 열기

## 소스로 실행

```
pip install -r requirements.txt
python folder_popup.py "D:\Folders\게임"
```

## exe 직접 빌드

```
pip install pyinstaller
pyinstaller --noconsole --onefile --name FolderPopup folder_popup.py
```

태그(`v1.0.0` 등)를 푸시하면 GitHub Actions가 자동으로 빌드해 Releases에 올립니다.

## 설정 변경
`folder_popup.py` 상단의 `COLUMNS`, `ICON_SIZE`, `MAX_VISIBLE_ROWS`, 색상값 등을 수정하세요.
