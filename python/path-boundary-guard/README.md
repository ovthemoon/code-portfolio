# 폴더 경계 검사가 옆 폴더를 통과시키던 구멍

출처: OpenDesk (pathguard.py, 2026-06)

## 문제
AI 동료는 정해진 폴더 안에서만 파일을 다뤄야 한다. 파일 도구 4종이 각자 `realpath(경로).startswith(realpath(워크스페이스))`를 복붙해 쓰고 있었다. 끝에 구분자가 없어서 `agent1` 권한으로 `agent1-evil` 폴더에 들어갈 수 있었다.
macOS는 한글 파일 이름을 NFD로 저장한다. 허용 목록의 루트가 NFC이면 정상적인 한글 폴더가 거부됐다.

## 해결
- 검사를 `is_path_within` 한 함수로 모았다.
- 양쪽을 `realpath`로 풀어 심볼릭 링크와 `..`를 접고, NFC와 casefold로 정규화한 뒤 비교한다.
- 같거나 `base + 구분자`로 시작할 때만 내부로 본다.
- 한계는 코드에 적어 두었다. 하드링크와 검사 시점과 사용 시점 사이의 경합은 다루지 않는다.

## 코드
- `pathguard.py`: 원본 `pathguard.py` 전체(62줄)에서 주석만 정리했다.
- `test_pathguard.py`: 형제 접두사, 상위 경로 이동, 심볼릭 링크, NFC/NFD, 대소문자 테스트. 고치기 전 패턴을 `naive_contains`로 두고 같은 입력에서 통과하는 것을 보인다.

## 확인
```
cd python && python3 -m pytest path-boundary-guard
```
심볼릭 링크 테스트는 Windows에서 건너뛴다.

## 숫자와 조건
실제 악용 사례는 없다.

## 원본과 다른 점
- 내부 설계 문서와 다른 모듈을 가리키던 docstring 참조를 지웠다.
- 테스트에서 고정 경로 대신 `tmp_path`를 쓰고, 기준선 함수, 루트 base, 틸드 확장 테스트를 더했다.
