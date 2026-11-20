# 성격과 스스로 하는 말·행동 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 페비가 시간과 사건에 따라 바뀌는 상태(기운·심심함·기분)를 갖고, 그 상태가 동작 확률과 스스로 하는 짧은 말을 함께 정하게 한다.

**Architecture:** 상태는 Qt 없는 `Mood`(`mood.py`)가 갖고, `Pet`이 소유해 사건을 알리고 기분 이름을 `Chooser`에 넘긴다. 시간 흐름은 `PetApp`의 1초 poll이 실제 시계로 민다. 말하는 시점·대사 정리·예비 대사는 Qt 없는 `Speaker`(`speech.py`)가, 모델 요청과 말풍선은 `PetApp`이 맡는다. 배율과 예비 대사는 `personality.toml`에 둔다.

**Tech Stack:** Python 3.12, PySide6, tomllib, pytest (`uv run pytest`), Ollama `/api/chat`.

**Spec:** `docs/superpowers/specs/2026-11-20-personality-design.md`

## Global Constraints

- 상태 값 세 개(`energy`, `boredom`, `cheer`)는 모두 0~1로 잘린다.
- 기분 이름 우선순위: `sleepy`(energy < 0.3) > `sulky`(cheer < 0.3) > `bored`(boredom > 0.7) > `happy`(cheer > 0.8) > `calm`.
- 혼잣말: 첫 글자 6초, 전체 15초 제한. 첫 문장만, 60자 넘으면 자름. 직전 10개와 같으면 예비 대사.
- 사건 대사는 사건 종류별로 10분(600초)에 한 번까지.
- 평소 간격 기본 `[4, 10]`분. `bored`면 ×0.6, `sleepy`면 ×1.5.
- 혼잣말 실패 시 오류 문구를 띄우지 않는다. 스크롤 말풍선을 쓰지 않는다.
- 혼잣말은 대화 기록에 가장 최근 하나만 남는다. 상황 설명 메시지는 기록에 남지 않는다.
- 혼잣말 요청은 `cfg.keep_alive`를 그대로 보낸다(모델을 늘 올려 둠).
- 사용자에게 보이는 문구는 한국어 해요체. 코드 주석·식별자는 기존처럼 영어.
- `config.toml`의 `monologue` 기본값은 `true`.
- 새 모듈은 기존 관례대로 docstring 첫 줄에 역할과 "No Qt." 여부를 적는다.

## Review Focus

1. **혼잣말이 사용자 대화와 겹침** — 모델 답을 기다리는 중 사용자가 더블클릭해 말을 걸면, 늦게 도착한 혼잣말이 대화 말풍선을 덮지 않아야 한다. (Task 8 `test_user_chat_abandons_pending_speech`)
2. **Ollama가 꺼져 있음** — 혼잣말 때마다 오류 말풍선이 뜨지 않고 예비 대사가 조용히 나와야 한다. (Task 8 `test_speech_failure_uses_fallback_silently`)
3. **모델이 긴 답이나 코드블록을 돌려줌** — 스크롤 말풍선으로 화면을 가리지 않아야 한다. (Task 7 `test_clean_cuts_to_first_sentence_and_60_chars`, `test_clean_rejects_code_and_empty`)
4. **경계값에서 기분이 깜빡임** — energy가 0.30 근처를 오갈 때 동작 배율이 매 초 뒤집히지 않아야 한다. (Task 2 `test_name_has_hysteresis`)
5. **앱을 밤새 켜 둠 / 날짜가 바뀜** — 시간대 사건(lunch/evening/late_night)이 다음 날 다시 한 번씩 나와야 하고, 같은 날 두 번 나오지 않아야 한다. (Task 7 `test_clock_events_once_per_day`)

---

## File Structure

| 파일 | 역할 |
|---|---|
| Create `src/phoebe_pet/mood.py` | `Mood`: 세 값, 시간 흐름, 사건, 기분 이름. No Qt |
| Create `src/phoebe_pet/personality.py` | `personality.toml` 읽기와 검증 → `Personality`. No Qt |
| Create `src/phoebe_pet/speech.py` | `Speaker`: 언제 말할지, 상황 설명, 답 정리, 예비 대사. No Qt |
| Create `personality.toml` | 기본 배율과 예비 대사 (placeholder·phoebe 동작 이름 모두) |
| Modify `src/phoebe_pet/config.py` | `monologue=True`, `monologue_minutes` |
| Modify `src/phoebe_pet/behavior.py` | `Chooser`가 기분 배율을 곱함 |
| Modify `src/phoebe_pet/pet.py` | `Mood` 소유, 사건 알림, `mouse_near`, `speaking` 그림 바꾸기, 사건 큐 |
| Modify `src/phoebe_pet/chat.py` | `ChatSession.add_monologue` |
| Modify `src/phoebe_pet/app.py` | 기존 monologue 제거, 실제 시계 tick, 혼잣말 요청·타임아웃·표시, `main()` 연결 |
| Modify `src/phoebe_pet/dev_panel.py` | 상태 표시, "지금 말하기", "기분 바꾸기" |
| Modify `config.toml`, `README.md` | 설정 표, 조작, GPU 안내 |

---

### Task 1: 설정

**Files:**
- Modify: `src/phoebe_pet/config.py`, `config.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.monologue: bool = True`, `Config.monologue_minutes: tuple[float, float] = (4.0, 10.0)`

- [ ] **Step 1: Write the failing tests**

```python
def test_monologue_on_by_default():
    assert Config().monologue is True and Config().monologue_minutes == (4.0, 10.0)

def test_monologue_minutes_from_file(tmp_path):
    p = tmp_path / "config.toml"; p.write_text("monologue_minutes = [2, 5]", encoding="utf-8")
    assert load_config(p).monologue_minutes == (2.0, 5.0)

@pytest.mark.parametrize("text", ["monologue_minutes = [5, 2]", "monologue_minutes = [0, 3]", "monologue_minutes = [1]", 'monologue_minutes = "4"'])
def test_bad_monologue_minutes(tmp_path, text):
    p = tmp_path / "config.toml"; p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="monologue_minutes"):
        load_config(p)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_config.py -v` — Expected: the three new tests FAIL.
- [ ] **Step 3: Implement.** `_coerce` gains a tuple branch: a list of two numbers → `tuple[float, float]`; then check `0 < low <= high`, else `ValueError("config: 'monologue_minutes' ...")`. Set `monologue = true` and add `monologue_minutes = [4, 10]` with a Korean comment in `config.toml`.
- [ ] **Step 4: Run** `uv run pytest tests/test_config.py -v` — Expected: PASS. Existing `tests/test_app.py::test_monologue_off_by_default_never_fires` will now fail; leave it, Task 8 replaces the monologue tests.
- [ ] **Step 5: Commit** `feat: monologue on by default with configurable gap`

---

### Task 2: Mood

**Files:**
- Create: `src/phoebe_pet/mood.py`
- Test: `tests/test_mood.py`

**Interfaces:**
- Produces:
  - `NAMES = ("sleepy", "sulky", "bored", "happy", "calm")`
  - `SLEEP_ACTIONS = frozenset({"lie", "doze_off"})`, `RUN_ACTIONS = frozenset({"run"})`
  - `class Mood:` `__init__(self, now: datetime)`; attributes `energy`, `boredom`, `cheer: float`; `forced: str | None = None`
  - `tick(self, seconds: float, action: str, now: datetime, mouse_near: bool) -> None`
  - `on_interact(self) -> None` (boredom −0.3), `on_chat_done(self) -> None` (boredom −0.5, cheer +0.15), `on_throw(self, speed: float) -> None` (cheer −0.25 when `speed >= 300`), `on_resist(self, seconds: float) -> None` (cheer −0.1 when `seconds >= 1.0`)
  - `name` property → `forced` if set, else the hysteresis result

Values (per hour unless noted):

| | 규칙 |
|---|---|
| 시작 energy | 6–11시 0.8, 11–18시 0.6, 18–23시 0.45, 23–6시 0.3. boredom 0.2, cheer 0.6 |
| energy | `SLEEP_ACTIONS` 중 +0.6/h. 그 밖 −0.15/h, 23–6시면 ×2, `RUN_ACTIONS`면 ×2 (겹치면 ×4) |
| boredom | `mouse_near`면 −0.5/h, 아니면 +0.5/h |
| cheer | 0.6 쪽으로 0.2/h씩 다가감(넘치지 않음) |

Hysteresis: the name currently held gets a 0.05 margin in its own favour (`sleepy` holds while energy < 0.35, `bored` while boredom > 0.65, etc.). Pick the first name in priority order whose (margined) condition holds, else `calm`.

- [ ] **Step 1: Write the failing tests** (use `datetime(2026, 11, 20, h, m)`)

```python
def test_start_energy_follows_time_of_day():
    assert Mood(at(8)).energy == 0.8 and Mood(at(14)).energy == 0.6 and Mood(at(20)).energy == 0.45 and Mood(at(2)).energy == 0.3

def test_awake_energy_drops_and_sleep_restores():
    m = Mood(at(14)); m.tick(3600, "stand", at(15), False); assert m.energy == pytest.approx(0.45)
    m.tick(3600, "lie", at(16), False); assert m.energy == pytest.approx(1.0)  # clamped

def test_night_and_running_drain_faster():
    m = Mood(at(14)); m.energy = 0.9; m.tick(3600, "run", at(1), False); assert m.energy == pytest.approx(0.3)

def test_boredom_rises_alone_and_falls_with_mouse_near():
    m = Mood(at(14)); m.tick(3600, "stand", at(15), False); assert m.boredom == pytest.approx(0.7)
    m.tick(3600, "stand", at(16), True); assert m.boredom == pytest.approx(0.2)

def test_cheer_drifts_back_to_resting_value():
    m = Mood(at(14)); m.cheer = 0.1; m.tick(3600, "stand", at(15), False); assert m.cheer == pytest.approx(0.3)
    m.cheer = 0.65; m.tick(3600, "stand", at(16), False); assert m.cheer == pytest.approx(0.6)

def test_events():
    m = Mood(at(14)); m.on_throw(299); assert m.cheer == 0.6
    m.on_throw(800); assert m.cheer == pytest.approx(0.35)
    m.on_resist(0.5); assert m.cheer == pytest.approx(0.35)
    m.on_resist(2.0); assert m.cheer == pytest.approx(0.25)
    m.boredom = 0.9; m.on_chat_done(); assert m.boredom == pytest.approx(0.4) and m.cheer == pytest.approx(0.4)
    m.on_interact(); assert m.boredom == pytest.approx(0.1)

def test_name_priority():
    m = Mood(at(14)); assert m.name == "calm"
    m.cheer = 0.9; assert m.name == "happy"
    m.boredom = 0.8; assert m.name == "bored"
    m.cheer = 0.2; assert m.name == "sulky"
    m.energy = 0.1; assert m.name == "sleepy"

def test_name_has_hysteresis():
    m = Mood(at(14)); m.energy = 0.29; assert m.name == "sleepy"
    m.energy = 0.33; assert m.name == "sleepy"
    m.energy = 0.36; assert m.name == "calm"
    m.energy = 0.32; assert m.name == "calm"

def test_forced_name_wins():
    m = Mood(at(14)); m.forced = "bored"; assert m.name == "bored"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_mood.py -v` — Expected: FAIL (no module).
- [ ] **Step 3: Implement** `src/phoebe_pet/mood.py` per the table. `name` stores the last result so the margin applies on the next read.
- [ ] **Step 4: Run** `uv run pytest tests/test_mood.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: mood state that drifts with time and events`

---

### Task 3: personality.toml

**Files:**
- Create: `src/phoebe_pet/personality.py`, `personality.toml`
- Test: `tests/test_personality.py`

**Interfaces:**
- Consumes: `mood.NAMES`
- Produces:
  - `LINE_KEYS = NAMES + ("thrown", "woke", "released", "lunch", "evening", "late_night")`
  - `@dataclass(frozen=True) class Personality: affinity: dict[str, dict[str, float]]; lines: dict[str, tuple[str, ...]]`
  - `load_personality(path: Path) -> Personality` (missing file → empty `Personality({}, {})`)
  - `personality_file(root: Path, character: str) -> Path` (same rule as `app.actions_file`)

- [ ] **Step 1: Write the failing tests**

```python
def test_repo_file_loads_with_lines_for_every_key():
    p = load_personality(ROOT / "personality.toml")
    assert set(LINE_KEYS) <= set(p.lines) and all(p.lines[k] for k in LINE_KEYS)
    assert p.affinity["lie"]["sleepy"] > 1

def test_missing_file_is_empty(tmp_path):
    assert load_personality(tmp_path / "none.toml") == Personality({}, {})

def test_unknown_mood_name_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="'lie'.*'dreamy'"):
        load_personality(write(tmp_path, "[affinity.lie]\ndreamy = 2"))

def test_negative_factor_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="negative"):
        load_personality(write(tmp_path, "[affinity.lie]\nsleepy = -1"))

def test_lines_must_be_lists_of_text(tmp_path):
    with pytest.raises(ValueError, match="lines"):
        load_personality(write(tmp_path, '[lines]\nsleepy = "하암"'))

def test_character_folder_overrides(tmp_path):
    (tmp_path / "assets" / "fancy").mkdir(parents=True)
    own = tmp_path / "assets" / "fancy" / "personality.toml"; own.write_text("", encoding="utf-8")
    assert personality_file(tmp_path, "fancy") == own
    assert personality_file(tmp_path, "plain") == tmp_path / "personality.toml"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_personality.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** the loader (wrap `TypeError/AttributeError` into `ValueError` like `load_actions`; unknown line keys are allowed). Write `personality.toml` with a header comment in Korean explaining `[affinity.<동작>]` and `[lines]`, affinities at least for: `lie`, `doze_off`, `lie_down`, `sit`, `sit_down`, `sit_dangle`, `run`, `to_run`, `walk`, `to_walk`, `creep`, `look_up`, `wall_climb`, `ceiling_move` (sleepy favours lying/sitting and suppresses running/climbing; bored and happy favour moving; sulky favours sitting/creeping). 3–6 lines per key in Phoebe's voice (해요체, 방랑자님 at most once, no emoji — see `Modelfile` [말투]), each under 40 characters.
- [ ] **Step 4: Run** `uv run pytest tests/test_personality.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: personality.toml with mood affinities and fallback lines`

---

### Task 4: 기분 배율로 동작 고르기

**Files:**
- Modify: `src/phoebe_pet/behavior.py:124-136`
- Test: `tests/test_behavior.py`

**Interfaces:**
- Consumes: `Personality.affinity`
- Produces: `Chooser(actions, rng, affinity: dict[str, dict[str, float]] | None = None)`; `choose(self, current: str, idle_seconds: float, mood: str = "calm") -> str`

- [ ] **Step 1: Write the failing tests**

```python
def test_mood_affinity_multiplies_weight():
    # stand -> next has walk(5) and sit(2) among others; make sit dominant when sleepy
    rng = random.Random(1)
    c = Chooser(ACTIONS, rng, {"sit": {"sleepy": 1000}})
    picks = [c.choose("stand", 0, "sleepy") for _ in range(200)]
    assert picks.count("sit") > 190
    picks = [c.choose("stand", 0, "calm") for _ in range(200)]
    assert picks.count("sit") < 100

def test_affinity_for_unknown_action_is_ignored():
    Chooser(ACTIONS, random.Random(0), {"nope": {"sleepy": 3}}).choose("stand", 0, "sleepy")

def test_all_zero_after_affinity_falls_back_to_even():
    c = Chooser(ACTIONS, random.Random(0), {n: {"sleepy": 0} for n in ACTIONS})
    assert c.choose("stand", 0, "sleepy") in ACTIONS["stand"].next
```

- [ ] **Step 2: Run** `uv run pytest tests/test_behavior.py -v` — Expected: new tests FAIL.
- [ ] **Step 3: Implement**: weight × `affinity.get(name, {}).get(mood, 1.0)`; existing all-zero fallback stays.
- [ ] **Step 4: Run** `uv run pytest tests/test_behavior.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: mood shifts which action comes next`

---

### Task 5: Pet이 Mood를 갖고 사건을 알림

**Files:**
- Modify: `src/phoebe_pet/pet.py`
- Test: `tests/test_pet.py`

**Interfaces:**
- Consumes: `Mood` (Task 2), `Chooser.choose(..., mood)` (Task 4)
- Produces:
  - `Pet(..., speed=1.0, mood: Mood | None = None)`; `pet.mood: Mood` (default `Mood(datetime.now())`)
  - `pet.mouse_near: bool` — set every `tick` (cursor within `LOOK_RADIUS` of the body centre)
  - `pet.speaking: bool = False` — when true, mode is `AUTO` and action is `stand`, `_view` shows the `talk` frames (timed by `_elapsed`) instead of stand; nothing else changes
  - `pet._events: list[str]` (tests append to it directly) and `pet.take_events() -> list[str]` — returns and clears queued events: `"thrown"` (landed after a release with speed ≥ `GRAB_SPEED`), `"released"` (released after resisting ≥ `RESIST_AFTER`), `"woke"` (an action named `wake_up` starts)
  - Calls into mood: `grab` → `on_interact()`; `release` → `on_throw(speed)` and `on_resist(self._still)`; every `_chooser.choose` call passes `self.mood.name`

- [ ] **Step 1: Write the failing tests** (fixture `pet` from conftest; add a helper that runs ticks)

```python
def test_choose_receives_mood_name(pet, monkeypatch):
    seen = []
    monkeypatch.setattr(pet._chooser, "choose", lambda cur, idle, mood="calm": seen.append(mood) or "stand")
    pet.mood.forced = "sleepy"; pet._duration = 0; pet.tick(0.016, (9000, 9000))
    assert seen == ["sleepy"]

def test_hard_throw_queues_thrown_on_landing_and_lowers_cheer(pet):
    before = pet.mood.cheer
    pet.grab((500, 300)); pet.drag_to((500, 300), 0.05); pet.drag_to((1100, 300), 0.05); pet.release()
    assert pet.mood.cheer < before and pet.take_events() == []
    run_until(pet, lambda: pet.mode is Mode.AUTO)
    assert pet.take_events() == ["thrown"] and pet.take_events() == []

def test_release_after_struggling_queues_released(pet):
    pet.grab((500, 300))
    for _ in range(80): pet.drag_to((500, 300), 0.016)
    pet.release(); run_until(pet, lambda: pet.mode is Mode.AUTO)
    assert "released" in pet.take_events()

def test_wake_up_queues_woke(qapp):
    # assets/phoebe is not in git; load the repo actions.toml and add a copy of "stand" named "wake_up"
    actions = load_actions(ROOT / "actions.toml")
    actions["wake_up"] = dataclasses.replace(actions["stand"], name="wake_up")
    rng = random.Random(0)
    p = Pet(actions, Chooser(actions, rng), Bounds(0, 0, 1920, 1040), (128, 128), rng)
    p._start("wake_up"); assert p.take_events() == ["woke"]

def test_mouse_near(pet):
    pet.tick(0.016, (9000, 9000)); assert not pet.mouse_near
    cx = pet._body.x + 64; cy = pet._body.y + 64
    pet.tick(0.016, (int(cx), int(cy))); assert pet.mouse_near

def test_speaking_shows_talk_only_while_standing(pet):
    pet.force("stand"); pet.speaking = True
    assert pet.tick(0.016, (9000, 9000)).frame in pet._actions["talk"].frames
    assert pet.mode is Mode.AUTO and pet.action == "stand"
    pet.force("sit"); assert pet.tick(0.016, (9000, 9000)).frame not in pet._actions["talk"].frames
```

- [ ] **Step 2: Run** `uv run pytest tests/test_pet.py -v` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** in `pet.py` as in Interfaces. Remember the throw speed in `release` and emit `"thrown"` when `_tick_air` sets `land`. Don't let `speaking` touch `mode`, `_duration` or `_pending_chat`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: everything passes except the old monologue tests in `tests/test_app.py`.
- [ ] **Step 5: Commit** `feat: pet owns a mood, reports events, can talk while standing`

---

### Task 6: 혼잣말은 기록에 하나만

**Files:**
- Modify: `src/phoebe_pet/chat.py` (`ChatSession`)
- Test: `tests/test_chat.py`

**Interfaces:**
- Produces: `ChatSession.add_monologue(self, text: str) -> None` — appends `{"role": "assistant", "content": text}` and removes the previous entry this method added (by identity), wherever it sits. `reset()` forgets it. Remove `add_assistant` (only the old monologue used it).

- [ ] **Step 1: Write the failing tests**

```python
def test_only_latest_monologue_is_kept():
    s = ChatSession(Config()); s.add_monologue("하나")
    s.begin("안녕"); s.succeed("네")
    s.add_monologue("둘")
    assert [m["content"] for m in s.history] == ["안녕", "네", "둘"]

def test_blank_monologue_is_ignored():
    s = ChatSession(Config()); s.add_monologue("  "); assert s.history == []
```

- [ ] **Step 2: Run** `uv run pytest tests/test_chat.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/test_chat.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: keep only the latest monologue in chat history`

---

### Task 7: Speaker

**Files:**
- Create: `src/phoebe_pet/speech.py`
- Test: `tests/test_speech.py`

**Interfaces:**
- Consumes: `Personality.lines` (Task 3)
- Produces:
  - `MAX_CHARS = 60`, `RECENT = 10`, `EVENT_COOLDOWN = 600.0`, `EVENT_DELAY = (2.0, 5.0)`
  - `class Speaker:` `__init__(self, lines: dict[str, tuple[str, ...]], rng: random.Random, gap_minutes: tuple[float, float], now: datetime)`
  - `tick(self, seconds: float, mood: str) -> None` — advances the quiet clock and any pending event delay
  - `note_event(self, event: str, clock: float) -> None` — queues it unless the same kind fired within `EVENT_COOLDOWN` of `clock` (monotonic seconds); fires after a random `EVENT_DELAY`; a newer event replaces an unfired older one
  - `clock_event(self, now: datetime) -> str | None` — `"lunch"` at/after 12:00, `"evening"` at/after 18:00, `"late_night"` at/after 23:00 (or before 5:00, counting toward the previous day); each at most once per day; the first call after start doesn't fire for hours already past at start
  - `due(self) -> str | None` — the key to speak about now: a ready event name, else the mood name when the quiet clock passed the gap, else `None`. Gap is picked anew after each `spoke`/`reset_quiet` from `gap_minutes` × 60 × (0.6 if bored, 1.5 if sleepy, else 1) — scaled at the moment `due` is checked with the current mood
  - `drop_pending(self) -> None` — forget a queued event (used when the pet can't speak right now)
  - `reset_quiet(self) -> None` — the user talked; restart the gap
  - `situation(self, key: str, mood: str, action: str, now: datetime, quiet_seconds: float) -> str` — the Korean stage direction sent as the last user message
  - `clean(self, reply: str) -> str | None` — first sentence (split after `.`, `!`, `?`, `…`, `~` or newline, keeping the mark), stripped of quotes, cut to `MAX_CHARS` with `…` if longer; `None` if empty, contains a code fence, or equals one of the last `RECENT` lines
  - `fallback(self, key: str) -> str | None` — random line from `lines[key]`, avoiding the last `RECENT` lines when possible; `None` if the list is missing/empty (the caller then tries the mood name as the key)
  - `spoke(self, line: str) -> None` — record in recent, restart the gap

Situation text shape (exact wording left to the implementer, these parts required):
`(지금은 {오전/오후} {h}시 {m}분. 페비는 {기분 풀이}. {사건 풀이 또는 지금 동작 풀이}. 방랑자님은 {N}분째 말이 없다. 페비가 혼잣말처럼 짧게 한 문장만 말한다. 20자 안팎.)`

- [ ] **Step 1: Write the failing tests**

```python
def test_mood_line_due_after_gap(speaker):            # gap (4,10) min, rng seeded
    speaker.tick(3 * 60, "calm"); assert speaker.due() is None
    speaker.tick(8 * 60, "calm"); assert speaker.due() == "calm"

def test_bored_speaks_sooner_than_sleepy():
    fast, slow = make(gap=(10, 10)), make(gap=(10, 10))
    fast.tick(7 * 60, "bored"); slow.tick(14 * 60, "sleepy")
    assert fast.due() == "bored" and slow.due() is None

def test_event_waits_a_moment_then_wins(speaker):
    speaker.note_event("thrown", clock=100.0); assert speaker.due() is None
    speaker.tick(5.0, "calm"); assert speaker.due() == "thrown"

def test_event_cooldown(speaker):
    speaker.note_event("thrown", 100.0); speaker.tick(5, "calm"); speaker.spoke("앗")
    speaker.note_event("thrown", 400.0); speaker.tick(5, "calm"); assert speaker.due() is None
    speaker.note_event("thrown", 800.0); speaker.tick(5, "calm"); assert speaker.due() == "thrown"

def test_clock_events_once_per_day():
    s = make(now=at(11, 0))
    assert s.clock_event(at(11, 59)) is None and s.clock_event(at(12, 0)) == "lunch" and s.clock_event(at(12, 30)) is None
    assert s.clock_event(at(18, 1)) == "evening" and s.clock_event(at(23, 5)) == "late_night"
    assert s.clock_event(at(1, 0, day=21)) is None  # still the 20th's night
    assert s.clock_event(at(12, 0, day=21)) == "lunch"

def test_clock_events_skip_hours_past_at_start():
    assert make(now=at(19, 0)).clock_event(at(19, 1)) is None

def test_clean_cuts_to_first_sentence_and_60_chars(speaker):
    assert speaker.clean("구름이 예뻐요. 그리고 또...") == "구름이 예뻐요."
    assert speaker.clean('"하암..."') == "하암..."
    long = "가" * 80
    assert speaker.clean(long) == "가" * 59 + "…"

def test_clean_rejects_code_and_empty(speaker):
    assert speaker.clean("  ") is None and speaker.clean("```py\nx\n```") is None

def test_clean_rejects_recent_repeat(speaker):
    speaker.spoke("하암, 졸려요."); assert speaker.clean("하암, 졸려요.") is None

def test_fallback_avoids_recent_and_handles_missing():
    s = make(lines={"sleepy": ("A", "B")}); s.spoke("A")
    assert s.fallback("sleepy") == "B" and s.fallback("bored") is None

def test_situation_mentions_time_mood_and_event(speaker):
    text = speaker.situation("thrown", "sulky", "stand", at(23, 20), 600)
    assert "오후 11시 20분" in text and "10분" in text and text.startswith("(") and text.endswith(")")
```

- [ ] **Step 2: Run** `uv run pytest tests/test_speech.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `speech.py`. Keep `quiet_seconds` as a readable property for `PetApp`.
- [ ] **Step 4: Run** `uv run pytest tests/test_speech.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: speaker decides when and what the pet says`

---

### Task 8: PetApp 연결

**Files:**
- Modify: `src/phoebe_pet/app.py`
- Test: `tests/test_app.py` (delete the five old monologue tests and `app_state_monologue_on`; add the ones below)

**Interfaces:**
- Consumes: Tasks 1–7
- Produces:
  - `PetApp(cfg, pet, window, bubble, input, session, worker_factory=ChatWorker, speaker: Speaker | None = None, clock=time.monotonic, now=datetime.now)`; a default `Speaker` built from an empty `Personality` when `None`
  - `life_tick(self, seconds: float) -> None` replaces `idle_tick`: `pet.mood.tick(seconds, pet.action, self._now(), pet.mouse_near)`; feeds `pet.take_events()` and `speaker.clock_event(...)` into `speaker.note_event`; `speaker.tick`; then if `speaker.due()` and `can_speak()` → `speak(key)`; if due but not `can_speak()` → `speaker.drop_pending()`
  - `poll()` passes the real elapsed seconds since the last poll (via `clock`), not `POLL_MS`
  - `can_speak(self) -> bool`: `cfg.monologue`, phase `IDLE`, not `session.busy`, window visible, input hidden, bubble hidden, `pet.mode is Mode.AUTO`, and no speech request already waiting
  - `speak(self, key: str) -> None` (also used by the developer panel): if a previous speech worker is still running → show fallback at once; else start `self.speech_worker` with `session.payload([{"role": "user", "content": speaker.situation(...)}])`, arm `first_ms=6000` and `total_ms=15000` single-shot timers (attributes so tests can shrink them)
  - On done → `speaker.clean`; `None` → fallback(key) or fallback(mood name). Fail or timeout → same fallback. Any result arriving after abandon is ignored (compare against a request counter, not the worker object)
  - `_show_speech(line)`: re-check `can_speak()` minus the "request waiting" clause; if false, drop it; else `bubble.show_notice(line)`, `pet.speaking = True`, `session.add_monologue(line)`, `speaker.spoke(line)`
  - Bubble `closed` → `pet.speaking = False`
  - `open_input` / `submit`: abandon a waiting speech, hide a speech bubble with `bubble.start()`, `pet.speaking = False`, `pet.mood.on_interact()`, `speaker.reset_quiet()`
  - User chat `_on_done` → `pet.mood.on_chat_done()`
  - `main()`: load `personality_file(ROOT, cfg.character)` (errors go to the existing start-up message box), build `Chooser(actions, rng, personality.affinity)`, `Speaker(personality.lines, rng, cfg.monologue_minutes, datetime.now())`
  - Remove `MONOLOGUE_PROMPT`, `MONOLOGUE_GAP`, `_monologue`, `monologue_after`, `_quiet`, `_last_idle`
  - `shutdown()` also stops the speech timers and interrupts/waits the speech worker

- [ ] **Step 1: Write the failing tests.** Fixture `app_live` builds `PetApp` with `Config(monologue=True)`, `FakeWorker`, a `Speaker` with `lines={"calm": ("평온한 말",), "thrown": ("앗!",), ...}` and `gap_minutes=(1, 1)`, fixed `now`, and puts the pet on the floor in `stand`.

```python
def test_speaks_after_gap_with_situation_prompt(app_live):
    app_live.life_tick(30); assert app_live.speech_worker is None
    app_live.life_tick(40)
    msg = app_live.speech_worker.payload["messages"][-1]
    assert msg["role"] == "user" and msg["content"].startswith("(")

def test_reply_shows_short_bubble_and_records_one_monologue(app_live, session, pet):
    app_live.speak("calm"); app_live.speech_worker.done.emit("구름이 예뻐요. 더 말하면...")
    assert app_live.bubble.text() == "구름이 예뻐요." and not app_live.bubble.is_scroll_mode()
    assert session.history == [{"role": "assistant", "content": "구름이 예뻐요."}] and pet.speaking
    app_live.bubble.closed.emit(); assert not pet.speaking

def test_speech_failure_uses_fallback_silently(app_live):
    app_live.speak("calm"); app_live.speech_worker.failed.emit(MSG_OFFLINE)
    assert app_live.bubble.text() == "평온한 말"

def test_slow_first_token_falls_back_and_late_reply_is_ignored(app_live):
    app_live.first_ms = 10; app_live.speak("calm"); worker = app_live.speech_worker
    QTest.qWait(50); assert app_live.bubble.text() == "평온한 말"
    worker.done.emit("늦은 답"); assert app_live.bubble.text() == "평온한 말"

def test_total_timeout_falls_back(app_live):
    app_live.total_ms = 30; app_live.speak("calm"); app_live.speech_worker.delta.emit("구름")
    QTest.qWait(80); assert app_live.bubble.text() == "평온한 말"

def test_user_chat_abandons_pending_speech(app_live):
    app_live.speak("calm"); speech = app_live.speech_worker
    app_live.input.submitted.emit("안녕"); assert app_live.worker.started
    speech.done.emit("혼잣말"); assert app_live.bubble.text() != "혼잣말"

@pytest.mark.parametrize("block", ["paused", "dragged", "hidden", "input_open", "user_chat_bubble"])
def test_never_speaks_when_it_should_not(app_live, pet, win, block):
    {"paused": lambda: app_live.toggle_pause(),
     "dragged": lambda: pet.grab((500, 300)),
     "hidden": lambda: app_live.toggle_hidden(),
     "input_open": lambda: app_live.input.open_at(win.geometry()),
     "user_chat_bubble": lambda: (app_live.input.submitted.emit("안녕"), app_live.worker.done.emit("네")),
    }[block]()
    app_live.life_tick(120)
    assert app_live.speech_worker is None

def test_monologue_off_changes_mood_but_never_speaks(app_live_off, pet):  # same fixture with Config(monologue=False)
    app_live_off.life_tick(3600); assert app_live_off.speech_worker is None and pet.mood.boredom > 0.2

def test_thrown_event_triggers_thrown_line(app_live, pet):
    pet._events.append("thrown"); app_live.life_tick(1); app_live.life_tick(5)
    assert app_live.speech_worker is not None
    app_live.speech_worker.failed.emit("x"); assert app_live.bubble.text() == "앗!"

def test_mood_ticks_while_hidden(app_live, pet):
    app_live.toggle_hidden(); before = pet.mood.boredom; app_live.life_tick(600); assert pet.mood.boredom > before
```

- [ ] **Step 2: Run** `uv run pytest tests/test_app.py -v` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** in `app.py` per Interfaces.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all PASS.
- [ ] **Step 5: Run the app** `uv run python -m phoebe_pet` with `monologue_minutes = [1, 1]` temporarily; with Ollama running, a short line appears within ~1–2 minutes; with Ollama stopped, a fallback line appears and no error bubble. Restore the setting.
- [ ] **Step 6: Commit** `feat: pet speaks on its own from mood and events`

---

### Task 9: 개발자 패널

**Files:**
- Modify: `src/phoebe_pet/dev_panel.py`, `src/phoebe_pet/app.py` (`open_dev_panel`)
- Test: `tests/test_dev_panel.py`

**Interfaces:**
- Consumes: `pet.mood`, `PetApp.speak`, `Speaker.quiet_seconds` and the current gap
- Produces: `DevPanel(pet, speak_now: Callable[[], None] | None = None, next_speech: Callable[[], float | None] | None = None)`; `panel.speak_button`, `panel.mood_button`; status line gains `기운 0.62  심심함 0.40  기분 0.55  [calm]  다음 혼잣말 3분 12초`

- [ ] **Step 1: Write the failing tests**

```python
def test_status_shows_mood(panel, pet):
    pet.mood.energy = 0.62; panel.refresh(); assert "기운 0.62" in panel.status.text() and "[calm]" in panel.status.text()

def test_mood_button_cycles_forced_names(panel, pet):
    seen = []
    for _ in range(6): panel.mood_button.click(); seen.append(pet.mood.forced)
    assert seen == ["sleepy", "sulky", "bored", "happy", "calm", None]

def test_speak_button_calls_back(qapp, pet):
    calls = []; p = DevPanel(pet, speak_now=lambda: calls.append(1)); p.speak_button.click(); assert calls == [1]; p.timer.stop(); p.close()

def test_speak_button_disabled_without_callback(panel):
    assert not panel.speak_button.isEnabled()
```

- [ ] **Step 2: Run** `uv run pytest tests/test_dev_panel.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement.** `PetApp.open_dev_panel` passes `speak_now=lambda: self.speak(self.pet.mood.name)` (only when `can_speak()` ignoring `cfg.monologue`) and `next_speech` returning seconds left.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: developer panel shows mood and can make the pet speak`

---

### Task 10: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** 설정 표: `monologue` 기본 `true`, 설명 "몇 분마다 기분과 상황에 맞춰 짧게 혼잣말을 합니다. 끄면 말만 안 하고 기분에 따른 움직임은 그대로". `monologue_minutes` `[4, 10]` 행 추가.
- [ ] **Step 2:** 새 절 "성격" — 기운·심심함·기분이 무엇에 따라 바뀌는지 3~5줄, `personality.toml`(배율, 예비 대사, 캐릭터 폴더에 두면 그쪽 우선), 혼잣말 중에도 대화 모델이 GPU에 계속 올라가 있으니 GPU를 비우려면 `monologue = false`.
- [ ] **Step 3:** 개발자 패널 설명에 상태 표시와 두 버튼 추가.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `docs: personality and monologue in README`
