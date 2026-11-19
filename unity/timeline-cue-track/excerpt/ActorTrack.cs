// 발췌: Timeline 트랙에서 배우에게 큐를 한 번씩 내리는 부분 (파일 전체). 원본은 Unity Timeline 에 의존해 빌드에서 제외한다.
// namespace 를 걷어 내고 주석을 정리했다. ActorCueBehaviour(Type, Fired 등 큐 데이터), StudioActor 등은 발췌에 없다.

using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

public sealed class ActorMixerBehaviour : PlayableBehaviour
{
    private bool _warnedUnresolved;

    public override void ProcessFrame(Playable playable, FrameData info, object playerData)
    {
        if (!Application.isPlaying)
        {
            return; // 편집 모드 스크럽에선 런타임 시스템(A*/착석)을 못 돌리므로 재생 전용
        }

        var actorSo = playerData as StudioActorSO;
        var actor = actorSo != null && StudioDirector.Instance != null
            ? StudioDirector.Instance.Resolve(actorSo)
            : null;
        if (actor == null)
        {
            // 조용히 넘기지 않는다. 바인딩 SO 가 캐스트에 없으면 큐 전체가 버려지므로 한 번만 경고한다.
            if (!_warnedUnresolved)
            {
                _warnedUnresolved = true;
                Debug.LogWarning(actorSo == null
                    ? "[Studio] ActorTrack 에 배우 SO 바인딩이 없습니다 — 이 트랙의 큐는 무시됩니다."
                    : $"[Studio] 트랙 바인딩 '{actorSo.name}' 가 StudioDirector 캐스트에 없습니다 — " +
                      "_cast 의 Actor 와 정확히 같은 에셋인지 확인하세요. 이 트랙의 큐는 무시됩니다.");
            }
            return;
        }

        int inputCount = playable.GetInputCount();
        for (int i = 0; i < inputCount; i++)
        {
            if (playable.GetInputWeight(i) <= 0f)
            {
                continue;
            }
            var input = (ScriptPlayable<ActorCueBehaviour>)playable.GetInput(i);
            var cue = input.GetBehaviour();
            if (cue.Fired)
            {
                continue;
            }
            cue.Fired = true;
            Fire(actor, cue, (float)input.GetDuration());
        }
    }

    private static void Fire(StudioActor actor, ActorCueBehaviour cue, float clipDuration)
    {
        switch (cue.Type)
        {
            case ActorCueType.Walk:
                if (cue.WalkTarget == null)
                {
                    Debug.LogWarning($"[Studio] {actor.DisplayName}: Walk 큐에 목적지 마커가 없습니다.");
                    return;
                }
                actor.WalkTo(cue.WalkTarget.position);
                break;
            case ActorCueType.Sit:
                actor.SitAtHomeDesk();
                break;
            case ActorCueType.HudState:
                actor.SetHud(cue.HudState, cue.StatusText);
                break;
            case ActorCueType.Expression:
                actor.SetExpression(cue.Key, clipDuration);
                break;
            case ActorCueType.Gesture:
                actor.PlayGesture(cue.Key, clipDuration);
                break;
            case ActorCueType.FaceCamera:
                actor.FaceCamera(cue.FaceMode, cue.LookUp);
                break;
            case ActorCueType.FaceActor:
            {
                if (cue.FaceTarget == null)
                {
                    Debug.LogWarning($"[Studio] {actor.DisplayName}: FaceActor 큐에 상대 배우가 없습니다.");
                    return;
                }
                var target = StudioDirector.Instance != null
                    ? StudioDirector.Instance.Resolve(cue.FaceTarget)
                    : null;
                if (target == null)
                {
                    Debug.LogWarning($"[Studio] {actor.DisplayName}: FaceActor 대상 '{cue.FaceTarget.name}' 가 " +
                                     "캐스트에 없습니다 — 큐를 무시합니다.");
                    return;
                }
                actor.FaceActor(target.transform, cue.FaceMode, cue.LookUp);
                break;
            }
            case ActorCueType.Speech:
                actor.Say(cue.SpeechText, clipDuration);
                break;
        }
    }
}

[TrackColor(0.35f, 0.62f, 0.85f)]
[TrackClipType(typeof(ActorCueClip))]
[TrackBindingType(typeof(StudioActorSO))]
public sealed class ActorTrack : TrackAsset
{
    public override Playable CreateTrackMixer(PlayableGraph graph, GameObject go, int inputCount)
    {
        return ScriptPlayable<ActorMixerBehaviour>.Create(graph, inputCount);
    }
}
