# 영웅을 교체하면 지속 효과가 매 프레임 오류를 내던 Unity "가짜 null"

출처: 무림 히어로즈 (EffectTargetLifetime.cs, EffectManager.cs, EffectDestroyedCasterTests.cs, 2026-10)

## 문제
Unity 오브젝트는 파괴돼도 C# 참조가 남고, `== null` 오버로드만 파괴를 null로 본다. 효과 시스템은 시전자를 인터페이스(`IEffectTarget`)로 들고 있어 이 오버로드가 걸리지 않고, `?.`도 그대로 통과한다. 영웅을 교체한 뒤 지속 효과가 파괴된 시전자의 transform을 읽어 매 프레임 `MissingReferenceException`이 났다. 예외가 갱신 루프 중간에서 터져, 그 적의 나머지 효과(만료 제거 포함)도 그 프레임에 처리되지 않았다.

## 해결
- 파괴 판정을 한 곳에 둔다: `target is Object o && o == null`. 시전자가 없는 경우(null)는 파괴가 아니므로 구분한다.
- 시전자를 인터페이스로 들고 있다가 나중에 다시 읽는 곳(효과 적용, 지속 효과 틱, 투사체 비행 중, 스킬 경계 판정)이 이 판정을 거친다.
- 파괴된 시전자의 지속 피해와 지속 회복은 즉시 끝낸다. 함께 중첩한 살아 있는 시전자가 있으면 이어받는다. 틱이 없는 버프와 디버프는 시전자를 다시 읽지 않으므로 남은 시간만큼 유지한다.

## 코드
- `excerpt/EffectTargetLifetime.cs`: 파괴 판정과 안전한 transform 읽기 (파일 전체)
- `excerpt/EffectManager.Guards.cs`: 효과 적용, 틱, 시전자 인계에서 판정을 쓰는 구간
- `excerpt/EffectDestroyedCasterTests.Excerpt.cs`: 파괴된 시전자, 시전자 없음, 디버프 유지 케이스

## 확인
발췌만 (원본은 Unity 의존). 테스트는 실제 `GameObject`를 파괴하는 Unity EditMode 테스트다.

## 숫자와 조건
- 2026-10-01 원본 게임의 전투 시험용 씬(Character Lab) 실측: 영웅 교체 뒤 14초에 오류 1,428건.
- 수정 후 같은 방식의 시나리오(지속 효과를 더미 3기에 건 뒤 영웅 교체)에서 약 2,000프레임 동안 오류 0건.
- 테스트는 커밋 시점 4건이고 수정 전 2건이 실패했으며 수정 후 4건 통과했다. 이후 늘어 발췌와 개수가 다르다.

## 원본과 다른 점
- namespace를 걷어 내고 주석을 정리했다.
- `EffectManager`는 가드 구간만 발췌했고 생략한 부분은 `...`로 표시했다.
- 테스트는 일부만 발췌했고 테스트 지원 클래스(`MockEffectTarget`, `DestroyableEffectTarget`)는 포함하지 않는다.
