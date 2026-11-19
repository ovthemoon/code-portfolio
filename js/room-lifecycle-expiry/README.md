# 쓰지 않는 방은 스스로 사라지고, 방 코드가 겹치면 다시 뽑는다

출처: 교실 실시간 그림 릴레이 게임(외주) (lifecycle.mjs, worker.js, 2026-09)

## 문제
수업이 끝난 뒤에도 방이 남아 있으면 비용이 샌다. 납품 뒤에는 개발자가 옆에서 방을 지워 줄 수 없다. 방은 6자리 숫자 코드로 구분해서 새 방의 코드가 살아 있는 방과 겹칠 수도 있었다.

## 해결
- 방 수명은 세 시각 중 가장 이른 것으로 정한다: 만든 지 24시간, 마지막 활동 뒤 6시간, 사람이 모두 나간 뒤 10분 (`roomExpiry`).
- 인증을 마친 연결만 "사람이 있다"로 센다. 일반 요청이나 인증 실패한 연결은 유예 시간을 늘리지 못한다. 이미 빈 방을 다시 확인해도 `emptySince`는 그대로다 (`trackOccupancy`).
- 방을 만들 때 `emptySince`를 지금으로 시작한다. 아무도 들어오지 않은 방도 10분 뒤 만료된다.
- 방 코드가 살아 있는 방과 겹치면 새 후보를 뽑아 최대 5번 다시 시도하고, 그래도 안 되면 503으로 끝낸다. 만료된 방의 코드는 다시 쓸 수 있다 (`createRoomWithUniqueCode`).
- 만료된 방은 알람에서 저장소를 통째로 지운다 (발췌).

## 코드
- `lifecycle.mjs`: `roomExpiry`, `isExpired`, `trackOccupancy`
- `room-code.mjs`: 방 코드 생성, 점유 판정(`claimRoomCode`), 재시도(`createRoomWithUniqueCode`)
- `lifecycle.test.mjs`, `room-code.test.mjs`: 위 두 파일의 테스트
- `excerpt/relay-room-expiry.js`: 원본 Durable Object의 `initialize`, `alarm`과 방 생성 재시도 루프 발췌

## 확인
```
cd js/room-lifecycle-expiry && node --test
```
`excerpt/`는 발췌만 있다 (Cloudflare Durable Object 런타임 전용이라 실행하지 않는다). 방마다 하나인 Durable Object는 `Map`으로 대신해 테스트한다.

## 원본과 다른 점
- `trackOccupancy`는 room을 제자리에서 바꾸고 true나 false를 돌려주던 것을, 바뀌었으면 새 객체를, 아니면 같은 객체를 돌려주도록 바꿨다 (`next !== room`으로 저장 여부를 판단한다).
- 코드 점유 판정과 재시도 루프는 원본에서 Durable Object와 라우트 안에 섞여 있던 것을 떼어 비동기 함수 하나로 만들었다. 재시도 횟수와 방 코드 범위는 원본과 같다.
- 발췌에서 교사 인증, 요청 제한, 새 방 생성 중지 스위치, 한국어 오류 문구를 뺐다.
