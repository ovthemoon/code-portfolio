# code-portfolio

실제 프로젝트에서 겪은 문제와 해결을 사례별로 떼어 낸 코드 모음입니다. 원본 레포는 비공개라서, 사례마다 핵심 코드만 발췌하거나 의존성을 걷어내 혼자 실행되게 다시 구성했습니다. 폴더마다 README에 문제, 해결, 확인 방법, 원본과 다른 점을 적었습니다.

## 게임 클라이언트 (Unity, C#)

| 폴더 | 문제 | 실행 |
|---|---|---|
| [unity/combat-engagement-hysteresis](unity/combat-engagement-hysteresis) | 사거리 경계에서 전투와 접근 상태가 매 프레임 뒤집힘 | 테스트 |
| [unity/dash-stop-distance](unity/dash-stop-distance) | 돌진 스킬이 상대 몸 안까지 파고듦 | 테스트 |
| [unity/virtual-scroll-window](unity/virtual-scroll-window) | 우편 1,000개 목록을 보이는 줄만 만들어 재사용 | 테스트 |
| [unity/fake-null-guard](unity/fake-null-guard) | 파괴된 시전자가 인터페이스 참조에서 null 검사를 통과 | 발췌 |
| [unity/composable-skill-actions](unity/composable-skill-actions) | 스킬을 작은 동작의 조합으로 만들고 씬 없이 테스트 | 발췌 |
| [unity/render-order-health-bar](unity/render-order-health-bar) | 카메라 설정 시점 때문에 체력바가 그려지지 않음 | 발췌 |
| [unity/approval-state-recount](unity/approval-state-recount) | 질문을 기다리는 AI 캐릭터가 쉬는 중으로 보임 | 발췌 |
| [unity/localization-deadlock-guard](unity/localization-deadlock-guard) | 불러오지 않은 번역 표를 동기 조회하다 화면이 멈춤 | 발췌 |
| [unity/timeline-cue-track](unity/timeline-cue-track) | 실제 앱 화면으로 영상을 찍는 Timeline 커스텀 트랙 | 발췌 |

## AI 에이전트 데몬과 서버 (Python)

| 폴더 | 문제 | 실행 |
|---|---|---|
| [python/mcp-read-only-retry](python/mcp-read-only-retry) | 끊긴 연결에 걸린 외부 도구 호출이 끝나지 않음 | 테스트 |
| [python/path-boundary-guard](python/path-boundary-guard) | 폴더 경계 검사가 옆 폴더를 통과시키고 한글 폴더를 거부 | 테스트 |
| [python/tool-call-weight](python/tool-call-weight) | AI가 물어볼 일과 알아서 할 일을 호출 하나 단위로 판정 | 테스트 |
| [python/missed-schedule-recovery](python/missed-schedule-recovery) | PC가 꺼진 동안 놓친 반복 작업 회차 복구 | 테스트 |
| [python/truncated-json-repair](python/truncated-json-repair) | 토큰 상한에 잘린 모델 JSON 응답 복구 | 테스트 |
| [python/sqlite-begin-immediate](python/sqlite-begin-immediate) | 동시 요청에서 SQLite "database is locked" | 테스트 |
| [python/payment-confirm-row-lock](python/payment-confirm-row-lock) | 결제 확정 경로 세 곳이 겹쳐 두 번 적립 | 테스트 |

## 실시간 웹 (JavaScript)

| 폴더 | 문제 | 실행 |
|---|---|---|
| [js/ws-push-hibernation](js/ws-push-hibernation) | 짧은 주기 폴링을 바뀔 때만 보내는 WebSocket으로 전환 | 테스트 |
| [js/idempotent-room-actions](js/idempotent-room-actions) | 재접속 뒤 같은 요청이 점수를 두 번 올림 | 테스트 |
| [js/server-side-view-projection](js/server-side-view-projection) | 교사, 학생, 중계 화면에 보는 사람별로 다른 정보 | 테스트 |
| [js/room-lifecycle-expiry](js/room-lifecycle-expiry) | 수업이 끝난 방을 자동으로 정리 | 테스트 |
| [js/realtime-wall-feed](js/realtime-wall-feed) | 끊기기 쉬운 모바일에서 실시간 벽 유지 | 테스트 |
| [js/note-submit-receipts](js/note-submit-receipts) | 재전송과 연타로 같은 글이 여러 번 올라감 | 테스트 |

## 실행

```bash
cd python && python3 -m pytest
```

```bash
cd js && node --test
```

```bash
cd unity && dotnet test
```

Python 3.14와 pytest 9, Node 22, .NET SDK 10에서 확인했습니다. C# 테스트는 net8.0 대상이라 .NET 8 이상이 필요합니다. 외부 패키지는 pytest와 C# 테스트용 NUnit뿐입니다.

## 참고

- 보안 임계값과 남용 제한 값은 원본 값이 아니라 예시값입니다. 해당 README에 표시했습니다.
- 숫자는 측정 조건과 함께 적었습니다. 조건이 확인되지 않은 숫자는 넣지 않았습니다.
