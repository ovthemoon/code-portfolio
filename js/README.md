# JavaScript 사례

Node 22 내장 `node:test`, ESM(`.mjs`), 외부 패키지 없음. 외주로 만든 두 실시간 웹 서비스에서 필요한 코드만 발췌하고, 단독으로 실행되도록 다시 정리했다. 원본은 비공개다.

| 폴더 | 문제 | 출처 |
|---|---|---|
| `ws-push-hibernation` | 계속 묻지 않고 바뀔 때만 알리고, 쉬는 동안은 깨우지 않는다 | 교실 실시간 그림 릴레이 게임(외주) |
| `idempotent-room-actions` | 끊겼다 다시 붙어도 같은 요청이 두 번 처리되지 않게 | 교실 실시간 그림 릴레이 게임(외주) |
| `server-side-view-projection` | 숨길 정보는 화면이 아니라 서버가 잘라서 보낸다 | 교실 실시간 그림 릴레이 게임(외주) |
| `room-lifecycle-expiry` | 쓰지 않는 방은 스스로 사라지고, 방 코드가 겹치면 다시 뽑는다 | 교실 실시간 그림 릴레이 게임(외주) |
| `realtime-wall-feed` | 실시간 벽은 읽기 전용 연결 하나로, 끊기면 느린 조회로 대신한다 | 밴드 팬 사이트의 실시간 한마디 벽(외주) |
| `note-submit-receipts` | 로그인 없는 한마디 벽에서 같은 제출이 두 번 들어가지 않게 | 밴드 팬 사이트의 실시간 한마디 벽(외주) |

## 실행
```
cd js && node --test
```
사례 하나만: `cd js/<폴더> && node --test`

`excerpt/` 폴더의 파일은 Cloudflare Durable Object나 브라우저 전용 코드를 발췌한 것이라 실행하지 않는다.
