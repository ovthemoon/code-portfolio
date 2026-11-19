# Unity 사례

Unity 프로젝트(무림 히어로즈, OpenDesk)의 코드 중 문제를 풀어 낸 부분만 모았다. 사례 하나가 폴더 하나이고, 각 폴더의 `README.md`에 문제, 해결, 확인 방법을 적었다.

실행 가능한 사례는 Unity 의존을 걷어 일반 C#으로 다시 썼고 NUnit 테스트가 있다. 나머지는 원본에서 발췌만 했고 `excerpt/` 아래에 있다. 원본 저장소는 비공개이고, 발췌는 비밀값과 미공개 게임 정보를 지웠다.

| 폴더 | 한 줄 | 형태 |
|---|---|---|
| [combat-engagement-hysteresis](combat-engagement-hysteresis) | 적 앞을 오가기만 하던 자동 전투 AI를 단일 공격 계획과 이중 경계선으로 고침 | 실행, 테스트 26개 |
| [dash-stop-distance](dash-stop-distance) | 돌진 뒤 몸통이 겹쳐 밀리던 문제를 반지름 합 기준 정지 거리로 고침 | 실행, 테스트 12개 |
| [virtual-scroll-window](virtual-scroll-window) | 우편 1,000개 목록의 보이는 행 계산과 행 재사용 | 실행, 테스트 27개, 원본 발췌 |
| [fake-null-guard](fake-null-guard) | 파괴된 Unity 오브젝트가 `?.`를 통과해 매 프레임 오류를 내던 문제 | 발췌만 |
| [composable-skill-actions](composable-skill-actions) | 스킬 동작을 작은 블록으로 나눠 조합하고 포트로 테스트하는 구조 | 발췌만 |
| [render-order-health-bar](render-order-health-bar) | 체력바만 안 그려지던 문제의 원인인 카메라 동기화 시점 | 발췌만 |
| [approval-state-recount](approval-state-recount) | 질문을 기다리는 AI가 쉬는 것처럼 보이던 상태를 대기 목록 재계산으로 바로잡음 | 발췌만 |
| [localization-deadlock-guard](localization-deadlock-guard) | 번역 표 동기 조회로 메인 스레드가 멈추던 교착과 미리 불러오기 | 발췌만 |
| [timeline-cue-track](timeline-cue-track) | 실제 앱 화면으로 영상을 찍는 Timeline 큐 트랙 | 발췌만 |

## 실행

.NET SDK 8 이상이 필요하다. 처음 실행할 때 NUnit 패키지를 내려받는다.

```
cd unity
dotnet test
```

- `src/CodePortfolio.Unity.csproj`: 각 사례 폴더 바로 아래의 `.cs`를 모은 라이브러리(netstandard2.1)
- `tests/CodePortfolio.Unity.Tests.csproj`: 각 사례 폴더의 `Tests/` 아래 `.cs`를 모은 테스트(net8.0, NUnit 3)
- `excerpt/` 아래 파일은 Unity에 의존하므로 빌드에 포함하지 않는다.
