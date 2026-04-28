from types import SimpleNamespace

from graph.nodes.step1_identify import step1_identify
import modules.memory as memory_mod
import modules.L2.sins_keyword as sins_mod
import modules.L2.collaboration_temperature as emotion_mod
import modules.L2.dual_core_recognition as dual_mod
import modules.L2.dimension_recognition as dimension_mod


def test_step1_populates_structured_memory_context(monkeypatch):
    fake_mgr = SimpleNamespace(
        get_unified_context=lambda **kwargs: '【用户画像】\n职业: 运营',
        update_emotion_pattern=lambda *args, **kwargs: None,
        update_desire_pattern=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(memory_mod, 'get_memory_manager', lambda: fake_mgr)
    monkeypatch.setattr(memory_mod, 'get_memory_context', lambda *args, **kwargs: 'fallback-text')
    monkeypatch.setattr(sins_mod, 'identify_desires', lambda text: SimpleNamespace(desires=SimpleNamespace(get_dominant=lambda: ('none', 0.0)), relations={}, confidence=0.9))
    monkeypatch.setattr(emotion_mod, 'identify_emotion', lambda text: SimpleNamespace(type='平静', intensity=0.1, confidence=0.9, motive='生活期待'))
    monkeypatch.setattr(dual_mod, 'identify_dual_core', lambda text: SimpleNamespace(state='协同', confidence=0.9))
    monkeypatch.setattr(dimension_mod, 'identify_dimensions', lambda text: SimpleNamespace(dominant_dimension='愿景'))

    class DesireState:
        fear = 0.0
        wrath = 0.0
        sloth = 0.0
        pride = 0.0

        def get_dominant(self):
            return ('none', 0.0)

    class EmotionState:
        type = SimpleNamespace(value='平静')
        intensity = 0.1
        confidence = 0.9

    class DualCoreStateObj:
        state = SimpleNamespace(value='协同')
        confidence = 0.9

    context = SimpleNamespace(
        session_id='step1-memory-test',
        short_utterance=False,
        history=[],
        user=SimpleNamespace(
            desires=DesireState(),
            emotion=EmotionState(),
            motive=None,
            dual_core=DualCoreStateObj(),
            attention=SimpleNamespace(focus=0.0, hijacked_by=None),
            relationship_position='',
        ),
        scene_config=None,
        self_state=SimpleNamespace(energy_mode=SimpleNamespace(value='A')),
        long_term_memory='',
        unified_context='',
        desire_relations={},
        _dimension_result=None,
        primary_scene='',
    )

    result = step1_identify({'context': context, 'user_input': '我想推进这件事'})

    out = result['context']
    assert out.unified_context.startswith('【用户画像】')
    assert out.long_term_memory.startswith('【用户画像】')
