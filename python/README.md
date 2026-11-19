# Python 사례

표준 라이브러리와 pytest만 쓴다. 사례 하나가 폴더 하나이고, 폴더마다 README와 테스트가 있다.

| 폴더 | 풀어낸 문제 |
|---|---|
| [mcp-read-only-retry](mcp-read-only-retry) | 끊긴 연결에 걸려 끝나지 않는 도구 호출을 시간 제한으로 끊고, 읽기로 확인된 호출만 한 번 다시 한다 |
| [path-boundary-guard](path-boundary-guard) | `agent1` 권한으로 `agent1-evil` 폴더에 들어가던 경계 검사와 macOS 한글 폴더 거부 |
| [tool-call-weight](tool-call-weight) | 도구 종류 단위 허락을, 호출 하나의 무게(되돌림, 받는 사람, 금액, 해 본 일)로 판정 |
| [missed-schedule-recovery](missed-schedule-recovery) | PC가 꺼져 있던 동안 지난 반복 업무 회차를 기록 없이 버리던 문제 |
| [truncated-json-repair](truncated-json-repair) | 토큰 상한에 잘린 모델 JSON에서 완성된 항목을 살리기 |
| [sqlite-begin-immediate](sqlite-begin-immediate) | 동시 요청에서 SQLite "database is locked"가 나던 읽기 후 쓰기 트랜잭션 |
| [payment-confirm-row-lock](payment-confirm-row-lock) | 결제 확정자 세 곳이 겹쳐 두 번 적립되던 문제 |

## 실행

```
cd python && python3 -m pytest
```

한 사례만: `python3 -m pytest sqlite-begin-immediate`. Python 3.14와 pytest 9.1에서 확인했다. 사례 폴더마다 모듈 이름이 달라서 한 번에 돌려도 충돌하지 않는다. `excerpt/` 폴더의 파일은 원본 발췌라 실행하지 않는다.
