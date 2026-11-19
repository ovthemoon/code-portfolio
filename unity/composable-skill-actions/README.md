# 스킬 동작을 작은 블록으로 나누고 조합해 실행하는 구조

출처: 무림 히어로즈 (ISkillAction.cs, ParallelAction.cs, ISkillCaster.cs, FakeSkillCaster.cs, 2025-11 ~ 2026-09)

## 문제
스킬의 동작(애니메이션 재생, 타격 대기, 데미지, 이펙트)을 스킬마다 개별 클래스로 구현하면, 순서나 조합을 바꿀 때마다 코드를 고쳐야 한다. 스킬 실행 코드가 시전자의 화면 컴포넌트에 직접 기대면 씬 없이는 시험할 수도 없다.

## 해결
- 동작 하나를 `ISkillAction`(비동기 실행 한 메서드와 요약 문자열)으로 만들고, 병렬, 조건, 반복 같은 조합도 같은 인터페이스를 구현한 액션으로 둔다. 순차는 스킬의 액션 목록 순서가 맡는다.
- `ParallelAction`은 자식 액션을 동시에 시작하고 모두 끝나야 끝난다. 자식 목록은 `[SerializeReference]`로 Inspector에서 조합한다.
- 스킬 실행이 시전자에 기대는 지점을 `ISkillCaster` 포트 하나에 가둔다. 테스트에서는 `FakeSkillCaster`로 바꿔 씬, 서버 없이 호출 기록을 확인한다.

## 코드
- `excerpt/ISkillAction.cs`: 액션 인터페이스 (파일 전체)
- `excerpt/ParallelAction.cs`: 병렬 조합 액션
- `excerpt/ISkillCaster.cs`: 시전자 포트 (파일 전체)
- `excerpt/FakeSkillCaster.cs`: 포트의 테스트 대역 (파일 전체)

## 확인
발췌만 (원본은 Unity와 UniTask 의존).

## 원본과 다른 점
- namespace와 using을 걷어 내고 주석을 정리했다. `SkillExecutionContext`, `EffectPool` 등 참조 타입은 발췌에 없다.
- `ParallelAction`에서 에디터 표시용 어트리뷰트(Odin)와 자식별 로깅 래퍼를 뺐고, 로거는 Unity `Debug`로 바꿨다.
- 조건 액션, 반복 액션과 스킬 본체 클래스는 발췌하지 않았다.
