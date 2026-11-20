# 페비 데스크톱 펫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시메지 규격 2D 캐릭터가 Windows 바탕화면을 돌아다니고, 더블클릭하면 로컬 Ollama `phoebe` 모델과 말풍선으로 대화하는 데스크톱 앱을 만든다.

**Architecture:** 물리·동작 선택·대화 기록 같은 로직은 Qt에 의존하지 않는 순수 Python 모듈로 두고 pytest로 검증한다. Qt 쪽은 얇게 유지한다: 스프라이트 크기의 투명 창 하나가 `Pet.tick()`이 돌려주는 위치·프레임을 그리기만 하고, 말풍선·입력창·트레이는 별도 창이다. 동작 정의는 `actions.toml` 데이터 파일이다.

**Tech Stack:** Python 3.12, PySide6, uv, pytest. HTTP는 표준 라이브러리 `urllib`. Win32 호출은 `ctypes`. 임시 캐릭터 그리기는 PySide6 `QPainter`.

**Spec:** `docs/2026-11-20-desktop-pet-design.md` (구현자는 이 문서도 함께 읽는다)

## Global Constraints

- Windows 11 전용. 앱은 GPU를 쓰지 않는다.
- Python 3.12, 의존성은 uv로 관리. 런타임 의존성은 `PySide6` 하나만.
- Ollama는 `http://localhost:11434`, 모델 `phoebe`, 요청에 `think: false`.
- 지형은 주 모니터 작업 영역(`QScreen.availableGeometry()`)의 네 변뿐이다. 다른 창 위 걷기, 다중 모니터는 만들지 않는다.
- CPU: 캐릭터가 멈춰 있을 때 전체 CPU 1% 이하, 움직일 때 3% 이하.
- 캐릭터 창은 포커스를 가져가지 않는다. 전체 화면 프로그램이 앞에 있으면 숨는다.
- 대화 기록은 메모리에만 둔다. 파일로 저장하지 않는다.
- 사용자에게 보이는 문구는 모두 한국어.
- 페비 그림은 저장소에 넣지 않는다. `assets/placeholder/`만 커밋한다.
- 소스 파일은 UTF-8. 커밋 메시지에 `Co-Authored-By` 줄을 넣지 않는다.
- 모든 명령은 `D:\study\phoebe-slack-bot`에서 실행한다. 테스트는 `uv run pytest`.

## Review Focus

1. **실행 중 해상도·작업 표시줄·배율 변경**: 캐릭터가 화면 밖에 남지 않고 새 작업 영역 안으로 들어와야 한다. → Task 5 `test_set_bounds_pulls_pet_inside`
2. **프레임이 몇 장뿐이거나 크기가 제각각인 이미지 세트**: `shime1.png` 한 장만 있어도 모든 동작이 돌아가야 한다. → Task 2 `test_single_frame_set_resolves_everything`
3. **아주 세게 던지거나 절전 복귀로 시간 간격이 커진 경우**: 캐릭터가 작업 영역을 벗어나지 않아야 한다. → Task 3 `test_huge_velocity_and_dt_stay_inside`
4. **답이 나오는 중에 또 메시지를 보냄**: 무시되고, 기록이 꼬이지 않아야 한다. → Task 7 `test_begin_while_busy_is_rejected`
5. **답 도중 연결이 끊기거나 Ollama가 오류를 돌려줌**: 한국어 안내가 뜨고, 실패한 턴은 기록에 남지 않아야 한다. → Task 7 `test_failed_turn_leaves_history_unchanged`, `test_error_line_raises`

## File Structure

```
pyproject.toml
config.toml                      사용자 설정 (기본값이 들어 있음)
actions.toml                     동작 정의 데이터
assets/placeholder/shime*.png    임시 캐릭터 (스크립트로 생성해 커밋)
tools/make_placeholder.py        임시 캐릭터 생성 스크립트
src/phoebe_pet/
  __main__.py                    진입점: python -m phoebe_pet
  config.py                      Config, load_config
  frames.py                      프레임 이름 대체 규칙 (순수)
  sprites.py                     SpriteSet: PNG 읽기, 배율, 좌우 반전 (Qt)
  physics.py                     Bounds, Body, step_air (순수)
  behavior.py                    Action, load_actions, Chooser (순수)
  pet.py                         Pet: 물리+동작+상호작용 상태 기계 (순수)
  chat.py                        ChatSession, parse_stream_line (순수) + ChatWorker (QThread)
  layout.py                      말풍선 위치·길이 판정·표시 시간 (순수)
  bubble.py                      BubbleWindow, InputWindow (Qt)
  pet_window.py                  PetWindow: 그리기, 마우스 입력, 타이머 (Qt)
  fullscreen.py                  전체 화면 감지 (ctypes)
  app.py                         모든 부품 연결, 트레이·메뉴
tests/                           test_<모듈>.py
```

---

### Task 1: 프로젝트 뼈대와 설정

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config.toml`, `src/phoebe_pet/__init__.py`, `src/phoebe_pet/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Config:
      character: str = "placeholder"   # assets/ 아래 폴더 이름
      scale: float = 1.0
      model: str = "phoebe"
      ollama_url: str = "http://localhost:11434"
      speed: float = 1.0               # 이동 속도 배율
      monologue: bool = False
      history_turns: int = 12
      keep_alive: str = "30m"
  def load_config(path: Path) -> Config
  ```

- [ ] **Step 1: 저장소 초기화.** `git init`, `uv init --package --name phoebe-pet --python 3.12`로 src 레이아웃을 만들고 `uv add PySide6`, `uv add --dev pytest`. `.gitignore`에 `.venv/`, `__pycache__/`, `assets/*/`, `!assets/placeholder/`를 넣는다. 기존 `Modelfile`, `test_chat.ps1`, `docs/`는 그대로 둔다.
- [ ] **Step 2: 실패하는 테스트 작성**

```python
def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "none.toml") == Config()

def test_values_override_defaults(tmp_path):
    p = tmp_path / "c.toml"; p.write_text('scale = 1.5\nmodel = "x"\n', encoding="utf-8")
    cfg = load_config(p)
    assert (cfg.scale, cfg.model, cfg.character) == (1.5, "x", "placeholder")

def test_unknown_key_ignored(tmp_path):
    p = tmp_path / "c.toml"; p.write_text('nope = 1\n', encoding="utf-8")
    assert load_config(p) == Config()

def test_wrong_type_names_the_key(tmp_path):
    p = tmp_path / "c.toml"; p.write_text('scale = "big"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="scale"):
        load_config(p)

def test_scale_out_of_range_rejected(tmp_path):
    p = tmp_path / "c.toml"; p.write_text('scale = 0\n', encoding="utf-8")
    with pytest.raises(ValueError, match="scale"):
        load_config(p)
```

- [ ] **Step 3: 실행해 실패 확인.** `uv run pytest tests/test_config.py -v` → import 오류로 FAIL.
- [ ] **Step 4: `config.py` 구현.** `tomllib` 사용. 정수는 float 필드에 허용. `scale`과 `speed`는 0.25~4.0, `history_turns`는 1 이상.
- [ ] **Step 5: `config.toml` 작성.** 모든 키를 기본값으로, 각 줄 위에 한국어 한 줄 설명 주석.
- [ ] **Step 6: 통과 확인 후 커밋.** `uv run pytest -v` → PASS. `git commit -m "feat: project scaffold and config loading"`

---

### Task 2: 스프라이트와 임시 캐릭터

**Files:**
- Create: `src/phoebe_pet/frames.py`, `src/phoebe_pet/sprites.py`, `tools/make_placeholder.py`, `assets/placeholder/*.png`
- Test: `tests/test_frames.py`, `tests/test_sprites.py`

**Interfaces:**
- Produces:
  ```python
  # frames.py
  FALLBACKS: dict[str, tuple[str, ...]]   # 프레임 이름 -> 대체 후보 순서
  def resolve(name: str, available: set[str]) -> str   # 최종 후보는 "shime1"
  class SpriteError(Exception)
  # sprites.py
  class SpriteSet:
      def __init__(self, folder: Path, scale: float) -> None   # shime1.png 없으면 SpriteError
      size: QSize                                              # shime1 크기 × scale
      def pixmap(self, name: str, facing_right: bool) -> QPixmap
  ```

- [ ] **Step 1: 시메지 표준 확인.** Shimeji-ee 원본 저장소의 기본 `conf/actions.xml`을 웹에서 찾아 아래 표와 대조한다. 다르면 **원본이 우선**이며, 이 표와 Task 4의 `actions.toml`을 원본에 맞게 고치고 차이를 커밋 메시지에 적는다. 원본을 찾지 못하면 아래 표대로 진행하고 그 사실을 보고한다.

  | 동작 | 프레임 |
  |---|---|
  | 서기 | 1 |
  | 걷기·달리기 | 1, 2, 1, 3 |
  | 낙하 | 4 |
  | 끌려가기(기울기 왼→오) | 9, 7, 5, 1, 6, 8, 10 |
  | 앉기 | 11 |
  | 벽 붙잡기 / 벽 타기 | 13 / 14, 14, 12, 13, 13, 12 |
  | 앉아서 고개 돌리기 | 26, 15, 27, 16, 28, 17, 29, 11 |
  | 착지 튕김 | 18, 19 |
  | 기어가기 / 눕기 | 20, 20, 21, 21, 21 / 21 |
  | 점프 | 22 |
  | 천장 붙잡기 / 천장 이동 | 23 / 25, 25, 23, 24, 24, 23 |
  | 올려다보기 | 26 |
  | 다리 올리고 앉기 / 다리 흔들기 | 30 / 31, 32, 31, 33 |

- [ ] **Step 2: 실패하는 테스트 작성**

```python
ALL_USED = {f"shime{i}" for i in range(1, 34)} | {"talk1", "talk2", "think1", "think2"}

def test_present_frame_resolves_to_itself():
    assert resolve("shime4", {"shime1", "shime4"}) == "shime4"

def test_single_frame_set_resolves_everything():
    assert {resolve(n, {"shime1"}) for n in ALL_USED} == {"shime1"}

def test_talk_falls_back_to_stand_and_think_to_sit():
    have = {"shime1", "shime11"}
    assert resolve("talk1", have) == "shime1"
    assert resolve("think1", have) == "shime11"

def test_fallback_prefers_same_motion_family():
    assert resolve("shime12", {"shime1", "shime13"}) == "shime13"   # 벽 타기 -> 벽 붙잡기
    assert resolve("shime24", {"shime1", "shime23"}) == "shime23"   # 천장 이동 -> 천장 붙잡기

# test_sprites.py — QT_QPA_PLATFORM=offscreen, QGuiApplication fixture
def test_missing_shime1_raises(tmp_path, qapp):
    with pytest.raises(SpriteError): SpriteSet(tmp_path, 1.0)

def test_scale_and_mixed_sizes(tmp_path, qapp):      # shime1 128x128, shime2 64x200 저장
    s = SpriteSet(tmp_path, 0.5)
    assert (s.size.width(), s.size.height()) == (64, 64)
    assert s.pixmap("shime2", False).size() == s.size   # 다른 크기는 비율 유지로 맞춰 가운데 아래 정렬

def test_facing_right_is_mirrored(tmp_path, qapp):   # 왼쪽 절반만 빨간 shime1
    s = SpriteSet(tmp_path, 1.0)
    assert s.pixmap("shime1", True).toImage().pixelColor(100, 64).red() == 255
```

- [ ] **Step 3: 실행해 실패 확인.** `uv run pytest tests/test_frames.py tests/test_sprites.py -v` → FAIL.
- [ ] **Step 4: `frames.py`, `sprites.py` 구현.** `SpriteSet`은 폴더의 PNG를 한 번만 읽고, (이름, 방향)별 변환 결과를 캐시한다. 배율 변환은 `Qt.SmoothTransformation`.
- [ ] **Step 5: `tools/make_placeholder.py` 작성.** `QPainter`로 128×128 투명 PNG를 그린다: 둥근 몸통, 눈 두 개, 짧은 팔다리로 된 단순한 캐릭터. `shime1`~`shime33`과 `talk1`, `talk2`, `think1`, `think2`를 모두 만들며, 프레임마다 자세가 눈으로 구별되어야 한다(걷기는 다리 위치, 벽 타기는 옆으로 붙은 자세, 천장은 거꾸로, 끌려가기는 기울기, 말하기는 입 모양). `uv run python tools/make_placeholder.py`로 `assets/placeholder/`에 생성한다.
- [ ] **Step 6: 통과 확인 후 커밋.** `uv run pytest -v` → PASS. 생성된 PNG 37장 포함. `git commit -m "feat: sprite loading with frame fallback and placeholder set"`

---

### Task 3: 물리

**Files:**
- Create: `src/phoebe_pet/physics.py`
- Test: `tests/test_physics.py`

**Interfaces:**
- Produces:
  ```python
  GRAVITY = 2400.0      # px/s^2
  MAX_SPEED = 3000.0    # px/s, 축별 상한
  MAX_DT = 0.05         # s, 이보다 큰 dt는 잘라서 쓴다
  @dataclass(frozen=True)
  class Bounds: left: int; top: int; right: int; bottom: int
  @dataclass
  class Body: x: float; y: float; vx: float; vy: float; w: int; h: int   # x, y는 왼쪽 위
  class Contact(Enum): NONE; FLOOR; LEFT_WALL; RIGHT_WALL; CEILING
  def step_air(body: Body, bounds: Bounds, dt: float) -> Contact   # 중력 적용, 이동, 경계에서 멈춤
  def clamp(body: Body, bounds: Bounds) -> None
  def on_floor(body: Body, bounds: Bounds) -> bool
  ```

- [ ] **Step 1: 실패하는 테스트 작성**

```python
B = Bounds(0, 0, 1920, 1040)
def body(**kw): return Body(**{"x": 900, "y": 100, "vx": 0, "vy": 0, "w": 128, "h": 128, **kw})

def test_falls_and_lands_exactly_on_floor():
    b = body(); contacts = [step_air(b, B, 1/60) for _ in range(600)]
    assert Contact.FLOOR in contacts and b.y == 1040 - 128 and b.vy == 0

def test_gravity_accelerates():
    b = body(); step_air(b, B, 0.01)
    assert b.vy == pytest.approx(24.0)

def test_thrown_left_hits_left_wall():
    b = body(x=50, vx=-2000, vy=-500)
    assert step_air(b, B, 0.05) == Contact.LEFT_WALL and b.x == 0 and b.vx == 0

def test_thrown_up_hits_ceiling():
    b = body(y=10, vy=-2000)
    assert step_air(b, B, 0.05) == Contact.CEILING and b.y == 0

def test_huge_velocity_and_dt_stay_inside():
    b = body(vx=1e9, vy=-1e9)
    for _ in range(100): step_air(b, B, 30.0)
    assert 0 <= b.x <= 1920 - 128 and 0 <= b.y <= 1040 - 128

def test_clamp_pulls_body_inside_smaller_bounds():
    b = body(x=1800, y=1000); clamp(b, Bounds(0, 0, 1280, 680))
    assert (b.x, b.y) == (1280 - 128, 680 - 128)

def test_bounds_smaller_than_body_do_not_crash():
    b = body(); clamp(b, Bounds(0, 0, 50, 50))
    assert (b.x, b.y) == (0, 0)
```

- [ ] **Step 2: 실행해 실패 확인.** `uv run pytest tests/test_physics.py -v` → FAIL.
- [ ] **Step 3: `physics.py` 구현.** 한 스텝에 접촉이 여럿이면 우선순위는 FLOOR, CEILING, 벽 순. 접촉한 축의 속도만 0으로 만든다.
- [ ] **Step 4: 통과 확인 후 커밋.** `git commit -m "feat: air physics with bounded integration"`

---

### Task 4: 동작 데이터와 선택기

**Files:**
- Create: `actions.toml`, `src/phoebe_pet/behavior.py`
- Test: `tests/test_behavior.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Action:
      name: str
      surface: str                 # "floor" | "wall" | "ceiling"
      frames: tuple[str, ...]
      frame_ms: int
      speed: float                 # 면을 따라 움직이는 속도 px/s. 0이면 제자리
      duration: tuple[float, float]  # 초 단위 최소, 최대
      weight: float
      idle_weight: float           # 60초 이상 건드리지 않았을 때 쓰는 가중치
      next: tuple[str, ...]        # 이 동작 뒤에 올 수 있는 동작 이름
      resting: bool                # True면 창이 느린 주기로 갱신
  IDLE_AFTER = 60.0
  def load_actions(path: Path) -> dict[str, Action]   # 검증 실패 시 ValueError
  class Chooser:
      def __init__(self, actions: dict[str, Action], rng: random.Random) -> None
      def choose(self, current: str, idle_seconds: float) -> str
      def duration(self, name: str) -> float
  ```
  특수 이름(동작 표에는 없고 `Pet`이 직접 다룸): `"fall"`, `"land"`, `"drag"`, `"think"`, `"talk"`, `"look_at_mouse"`. 이들의 프레임은 `actions.toml`의 `[special.<이름>]` 표에 `frames`, `frame_ms`만 둔다. `load_actions`는 이를 `Action`으로 읽되 `surface="floor"`, `next=()`로 채운다.

- [ ] **Step 1: `actions.toml` 작성.** `[action.<이름>]` 표로 다음을 정의한다. 프레임은 Task 2 Step 1에서 확정한 표를 따른다.

  | 이름 | 면 | 속도 | 지속(초) | 가중치 / 한가할 때 | next |
  |---|---|---|---|---|---|
  | stand | floor | 0 | 1~4 | 3 / 2 | walk, run, sit, look_up, stand |
  | walk | floor | 60 | 2~8 | 5 / 2 | stand |
  | run | floor | 180 | 1~3 | 1 / 0.2 | stand |
  | look_up | floor | 0 | 1~3 | 1 / 1 | stand |
  | sit | floor | 0 | 3~10 | 2 / 5 | stand, sit_spin, sit_dangle, lie |
  | sit_spin | floor | 0 | 2~4 | 1 / 1 | sit |
  | sit_dangle | floor | 0 | 3~8 | 1 / 3 | sit |
  | lie | floor | 0 | 5~20 | 1 / 6 | creep, sit |
  | creep | floor | 20 | 2~6 | 1 / 1 | lie |
  | wall_hold | wall | 0 | 1~3 | 2 / 2 | wall_climb, wall_hold |
  | wall_climb | wall | 50 | 2~6 | 4 / 2 | wall_hold |
  | ceiling_hold | ceiling | 0 | 1~3 | 2 / 2 | ceiling_move, ceiling_hold |
  | ceiling_move | ceiling | 40 | 2~6 | 4 / 2 | ceiling_hold |

  `resting`은 속도가 0인 동작 모두 true. `stand → lie`처럼 표에 없는 전이는 없다(연결 동작 규칙). 걷다가 벽에 닿아 벽을 타거나, 벽에서 손을 놓는 것은 `Pet`(Task 5)이 정한다.

- [ ] **Step 2: 실패하는 테스트 작성**

```python
ACTIONS = load_actions(Path("actions.toml"))

def test_repo_actions_file_loads_and_has_core_actions():
    assert {"stand", "walk", "sit", "lie", "wall_climb", "ceiling_move", "fall", "drag", "talk", "think"} <= set(ACTIONS)

def test_unknown_next_reference_rejected(tmp_path):   # next = ["nope"] 인 파일
    with pytest.raises(ValueError, match="nope"): load_actions(p)

def test_empty_frames_rejected(tmp_path):
    with pytest.raises(ValueError, match="frames"): load_actions(p)

def test_choice_always_comes_from_next():
    c = Chooser(ACTIONS, random.Random(1))
    for _ in range(500): assert c.choose("walk", 0) == "stand"
    assert {c.choose("sit", 0) for _ in range(500)} == {"stand", "sit_spin", "sit_dangle", "lie"}

def test_no_immediate_repeat_when_alternatives_exist():
    c = Chooser(ACTIONS, random.Random(2))
    assert "stand" not in {c.choose("stand", 0) for _ in range(500)}

def test_idle_shifts_toward_resting():
    def share(idle):
        c = Chooser(ACTIONS, random.Random(3))
        return sum(c.choose("stand", idle) == "sit" for _ in range(4000)) / 4000
    assert share(120) > share(0) + 0.15

def test_duration_within_range():
    c = Chooser(ACTIONS, random.Random(4))
    assert all(2 <= c.duration("walk") <= 8 for _ in range(200))
```

- [ ] **Step 3: 실행해 실패 확인.** `uv run pytest tests/test_behavior.py -v` → FAIL.
- [ ] **Step 4: `behavior.py` 구현.** 선택은 `rng.choices`에 가중치를 넘긴다. 후보에서 현재 동작을 빼되, 그러면 후보가 비는 경우에만 남긴다.
- [ ] **Step 5: 통과 확인 후 커밋.** `git commit -m "feat: data-driven actions and weighted chooser"`

---

### Task 5: Pet 상태 기계

**Files:**
- Create: `src/phoebe_pet/pet.py`
- Test: `tests/test_pet.py`

**Interfaces:**
- Consumes: Task 3의 `Bounds`, `Body`, `Contact`, `step_air`, `clamp`, `MAX_DT`; Task 4의 `Action`, `Chooser`.
- Produces:
  ```python
  class Mode(Enum): AUTO; AIR; DRAGGED; THINK; TALK; PAUSED
  @dataclass(frozen=True)
  class View: x: int; y: int; frame: str; facing_right: bool; resting: bool
  class Pet:
      def __init__(self, actions: dict[str, Action], chooser: Chooser, bounds: Bounds,
                   size: tuple[int, int], rng: random.Random, speed: float = 1.0) -> None
      mode: Mode
      action: str                      # 현재 동작 이름
      idle_seconds: float              # 마지막 상호작용 이후 흐른 시간
      def tick(self, dt: float, mouse: tuple[int, int]) -> View
      def grab(self, mouse: tuple[int, int]) -> None
      def drag_to(self, mouse: tuple[int, int], dt: float) -> None
      def release(self) -> None        # 최근 끌기 속도로 던진다
      def begin_think(self) -> None
      def begin_talk(self) -> None
      def end_chat(self) -> None
      def set_paused(self, paused: bool) -> None
      def set_bounds(self, bounds: Bounds) -> None
      def touch(self) -> None          # 한가한 시간 0으로
  ```

동작 규칙(테스트가 정하지 않는 부분):
- 시작 위치는 바닥 위 무작위 x, 동작 `stand`.
- `walk`/`run`/`creep` 속도는 동작 시작 0.3초 동안 0에서 목표 속도로, 끝나기 0.3초 전부터 0으로 선형 변화. 목표 속도에는 `speed` 배율을 곱한다.
- 바닥에서 움직이다 벽에 닿으면 50% 확률로 `wall_hold`(벽 쪽을 본다), 아니면 방향을 뒤집고 `stand`. 벽을 타고 올라 천장에 닿으면 `ceiling_hold`. 벽 타고 내려와 바닥에 닿으면 `stand`. 천장에서 이동하다 벽에 닿으면 방향을 뒤집는다.
- `wall_hold`, `ceiling_hold`의 지속 시간이 끝날 때마다 15% 확률로 손을 놓아 `AIR`가 된다.
- `AIR`: `step_air`로 이동, 프레임은 `fall`. `FLOOR` 접촉 시 `land` 프레임을 0.4초 보여 준 뒤 `stand`로 `AUTO`. 벽·천장 접촉 시 속도가 300px/s 이상이었으면 그 면을 붙잡고(`wall_hold`/`ceiling_hold`), 아니면 계속 떨어진다.
- `DRAGGED`: 창의 위쪽 가운데가 마우스를 따라간다. 프레임은 `drag`의 7장 중 수평 속도(-1200~+1200px/s를 7구간으로)에 따라 고른다. 속도는 최근 0.1초의 이동으로 추정한다.
- 마우스가 캐릭터 중심에서 200px 안에 있고 현재 동작이 `stand` 또는 `sit`이면 프레임을 `look_at_mouse`로 바꾸고 마우스 쪽을 본다(동작 자체는 유지).
- `begin_think()`: 바닥이 아니면 손을 놓고 떨어진 뒤, 착지하면 멈춰 서서 `think` 프레임. 바닥이면 즉시. `begin_talk()`는 `talk` 프레임. `end_chat()`은 `stand`로 `AUTO`.
- `PAUSED`: 현재 자리에서 `stand`로 고정. 끌기와 대화는 여전히 된다.
- `View.resting`은 `AUTO`에서 현재 동작의 `resting`이 참이고 `look_at_mouse`가 아닐 때, 그리고 `PAUSED`에서 참.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
B = Bounds(0, 0, 1920, 1040)
def make(seed=0):
    rng = random.Random(seed); acts = load_actions(Path("actions.toml"))
    return Pet(acts, Chooser(acts, rng), B, (128, 128), rng)
def run(pet, seconds, mouse=(-9999, -9999), dt=1/60):
    return [pet.tick(dt, mouse) for _ in range(int(seconds / dt))]
FAR = (-9999, -9999)

def test_starts_standing_on_floor():
    v = make().tick(0.0, FAR)
    assert v.y == 1040 - 128 and v.frame == "shime1"

@pytest.mark.parametrize("seed", range(20))
def test_ten_minutes_never_leaves_bounds_and_visits_variety(seed):
    pet = make(seed); seen = set()
    for v in run(pet, 600):
        assert 0 <= v.x <= 1920 - 128 and 0 <= v.y <= 1040 - 128
        seen.add(pet.action)
    assert len(seen) >= 6

def test_floor_actions_keep_feet_on_floor():
    pet = make(5)
    for v in run(pet, 120):
        if pet.mode is Mode.AUTO and pet.action in ("walk", "run", "sit", "lie", "creep"):
            assert v.y == 1040 - 128

def test_walk_eases_in():
    pet = make(); pet._start("walk")          # 테스트용 내부 진입점
    xs = [v.x for v in run(pet, 0.5)]
    first, later = abs(xs[5] - xs[0]), abs(xs[29] - xs[24])
    assert first < later

def test_grab_drag_release_throws_and_lands():
    pet = make(); pet.grab((960, 500))
    for i in range(10): pet.drag_to((960 + i * 30, 500), 1/60)
    assert pet.mode is Mode.DRAGGED
    pet.release(); assert pet.mode is Mode.AIR
    views = run(pet, 5)
    assert views[5].x > 960 and pet.mode is Mode.AUTO

def test_drag_frame_follows_horizontal_speed():
    pet = make(); pet.grab((960, 500))
    for i in range(10): pet.drag_to((960 + i * 30, 500), 1/60)
    fast_right = pet.tick(1/60, (1260, 500)).frame
    for _ in range(30): pet.drag_to((1260, 500), 1/60)
    still = pet.tick(1/60, (1260, 500)).frame
    assert fast_right != still

def test_chat_stops_wandering_then_resumes():
    pet = make(); pet.begin_think(); views = run(pet, 3)
    assert pet.mode is Mode.THINK and len({v.x for v in views}) == 1
    pet.begin_talk(); assert pet.tick(1/60, FAR).frame.startswith(("talk", "shime1"))
    pet.end_chat(); assert pet.mode is Mode.AUTO

def test_think_from_wall_drops_to_floor_first():
    pet = make(); pet._place_on_wall(left=True, y=300)
    pet.begin_think(); run(pet, 3)
    assert pet.mode is Mode.THINK and pet.tick(1/60, FAR).y == 1040 - 128

def test_paused_does_not_move_but_can_be_dragged():
    pet = make(); pet.set_paused(True)
    assert len({(v.x, v.y) for v in run(pet, 30)}) == 1
    pet.grab((500, 500)); assert pet.mode is Mode.DRAGGED

def test_set_bounds_pulls_pet_inside():
    pet = make(); pet.set_bounds(Bounds(0, 0, 800, 600)); v = pet.tick(1/60, FAR)
    assert 0 <= v.x <= 800 - 128 and 0 <= v.y <= 600 - 128
    run(pet, 5); assert pet.tick(1/60, FAR).y == 600 - 128     # 공중에 남지 않고 바닥으로

def test_long_gap_does_not_teleport():
    pet = make(); a = pet.tick(1/60, FAR); b = pet.tick(3600.0, FAR)
    assert abs(b.x - a.x) <= 180 * MAX_DT + 1

def test_resting_flag():
    pet = make(); pet._start("sit"); assert pet.tick(1/60, FAR).resting
    pet._start("walk"); assert not pet.tick(1/60, FAR).resting
    pet._start("sit"); cx = pet.tick(1/60, FAR).x + 64
    assert not pet.tick(1/60, (cx + 50, 1000)).resting          # 마우스를 쳐다보는 중

def test_touch_resets_idle():
    pet = make(); run(pet, 90); pet.touch(); assert pet.idle_seconds == 0
```

- [ ] **Step 2: 실행해 실패 확인.** `uv run pytest tests/test_pet.py -v` → FAIL.
- [ ] **Step 3: `pet.py` 구현.** `tick`은 맨 먼저 `dt = min(dt, MAX_DT)`. `_start(name)`과 `_place_on_wall(left, y)`는 테스트와 내부 전이가 같이 쓰는 진입점이다. `grab`·`begin_think`는 `touch()`를 부른다.
- [ ] **Step 4: 통과 확인 후 커밋.** `uv run pytest -v` → PASS. `git commit -m "feat: pet state machine with drag, throw and chat modes"`

---

### Task 6: 캐릭터 창

**Files:**
- Create: `src/phoebe_pet/pet_window.py`, `src/phoebe_pet/__main__.py`, `src/phoebe_pet/app.py`
- Test: `tests/test_pet_window.py`

**Interfaces:**
- Consumes: `Pet`, `View`, `SpriteSet`, `Config`, `load_config`, `load_actions`, `Chooser`, `Bounds`.
- Produces:
  ```python
  FAST_MS = 16; SLOW_MS = 100; DRAG_THRESHOLD = 4   # px
  class PetWindow(QWidget):
      double_clicked = Signal()
      context_requested = Signal(QPoint)      # 화면 좌표
      moved = Signal(QRect)                   # 창 위치가 바뀔 때
      def __init__(self, pet: Pet, sprites: SpriteSet) -> None
  # app.py
  def bounds_of(screen: QScreen) -> Bounds    # availableGeometry 기준
  def main() -> int                           # __main__.py가 호출
  ```

- [ ] **Step 1: 실패하는 테스트 작성** (`QT_QPA_PLATFORM=offscreen`, `qapp` fixture는 `tests/conftest.py`에 둔다)

```python
def test_window_flags(win):
    f = win.windowFlags()
    assert f & Qt.FramelessWindowHint and f & Qt.WindowStaysOnTopHint and f & Qt.Tool
    assert f & Qt.WindowDoesNotAcceptFocus
    assert win.testAttribute(Qt.WA_TranslucentBackground)
    assert win.testAttribute(Qt.WA_ShowWithoutActivating)

def test_size_matches_sprites(win, sprites):
    assert win.size() == sprites.size

def test_timer_slows_when_resting(win, pet):
    pet._start("sit"); win.step(); assert win.timer.interval() == SLOW_MS
    pet._start("walk"); win.step(); assert win.timer.interval() == FAST_MS

def test_press_without_move_is_not_a_drag(win, pet):
    QTest.mousePress(win, Qt.LeftButton, pos=QPoint(64, 64)); QTest.mouseRelease(win, Qt.LeftButton, pos=QPoint(64, 64))
    assert pet.mode is not Mode.AIR and pet.mode is not Mode.DRAGGED

def test_press_and_move_starts_drag_and_release_throws(win, pet):
    QTest.mousePress(win, Qt.LeftButton, pos=QPoint(64, 64)); QTest.mouseMove(win, QPoint(64 + 20, 64))
    assert pet.mode is Mode.DRAGGED
    QTest.mouseRelease(win, Qt.LeftButton, pos=QPoint(84, 64)); assert pet.mode is Mode.AIR

def test_double_click_emits_and_does_not_drag(win, pet):
    spy = QSignalSpy(win.double_clicked)
    QTest.mouseDClick(win, Qt.LeftButton, pos=QPoint(64, 64))
    assert spy.count() == 1 and pet.mode is not Mode.DRAGGED

def test_transparent_pixels_are_masked_out(win):
    assert not win.mask().contains(QPoint(0, 0))      # placeholder의 모서리는 투명
```

- [ ] **Step 2: 실행해 실패 확인.** `uv run pytest tests/test_pet_window.py -v` → FAIL.
- [ ] **Step 3: `PetWindow` 구현.** `step()`은 `QElapsedTimer`로 잰 dt와 `QCursor.pos()`로 `pet.tick`을 부르고, 창을 `View` 위치로 옮기고, 프레임이 바뀌었을 때만 `setMask(pixmap.mask())`와 `update()`를 한다. 투명 픽셀 클릭 통과는 이 마스크로 얻는다. 타이머 간격은 `View.resting`에 따라 `SLOW_MS`/`FAST_MS`. 끌기는 누른 뒤 `DRAG_THRESHOLD` 이상 움직였을 때 `pet.grab`을 부르고 `FAST_MS`로 전환한다. 우클릭은 `context_requested`.
- [ ] **Step 4: `app.py`의 `main()` 구현(최소).** 설정·동작·스프라이트를 읽어 `Pet`과 `PetWindow`를 만들고 띄운다. 캐릭터 폴더는 `assets/<character>`. `QScreen.availableGeometryChanged`에 `pet.set_bounds(bounds_of(screen))`을 연결한다. `QApplication.setQuitOnLastWindowClosed(False)`. 설정이나 이미지 오류는 `QMessageBox`로 한국어 안내 후 종료 코드 1.
- [ ] **Step 5: 통과 확인.** `uv run pytest -v` → PASS.
- [ ] **Step 6: 직접 실행해 확인.** `uv run python -m phoebe_pet`을 띄워 2분간 관찰한다. 확인 항목: 캐릭터가 작업 표시줄 위를 걷는다 / 앉고 눕는다 / 벽과 천장을 탄다 / 집어서 던지면 날아가 착지한다 / 캐릭터 주변 투명 영역을 클릭하면 뒤의 창이 클릭된다 / 다른 창에서 타이핑 중 포커스를 빼앗지 않는다. 화면을 캡처해 결과를 보고한다.
- [ ] **Step 7: 커밋.** `git commit -m "feat: transparent pet window with drag and adaptive tick"`

---

### Task 7: 대화 엔진

**Files:**
- Create: `src/phoebe_pet/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: `Config`.
- Produces:
  ```python
  class ChatError(Exception)        # str(e)는 사용자에게 그대로 보여 줄 한국어 문구
  MSG_OFFLINE = "Ollama가 꺼져 있는 것 같아요. 먼저 실행해 주세요."
  MSG_NO_MODEL = "'{model}' 모델을 찾을 수 없어요."
  MSG_BROKEN = "답을 받다가 연결이 끊겼어요. 다시 말해 주세요."
  def parse_stream_line(line: bytes) -> tuple[str, bool]    # (추가된 글자, 끝났는지)
  class ChatSession:
      def __init__(self, cfg: Config) -> None
      busy: bool
      history: list[dict]                              # {"role", "content"}
      def begin(self, user_text: str) -> dict | None   # 요청 본문. busy면 None
      def succeed(self, reply: str) -> None            # 사용자 말과 답을 기록에 추가
      def fail(self) -> None                           # 기록은 그대로
      def reset(self) -> None
  class ChatWorker(QThread):
      delta = Signal(str); done = Signal(str); failed = Signal(str)
      def __init__(self, url: str, payload: dict, model: str) -> None
  ```

- [ ] **Step 1: 실패하는 테스트 작성**

```python
CFG = Config(history_turns=2)

def test_payload_shape():
    p = ChatSession(CFG).begin("안녕")
    assert p["model"] == "phoebe" and p["stream"] is True and p["think"] is False
    assert p["keep_alive"] == "30m" and p["messages"] == [{"role": "user", "content": "안녕"}]

def test_history_grows_only_on_success():
    s = ChatSession(CFG); s.begin("a"); s.succeed("A")
    assert s.history == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "A"}] and not s.busy

def test_failed_turn_leaves_history_unchanged():
    s = ChatSession(CFG); s.begin("a"); s.succeed("A"); before = list(s.history)
    s.begin("b"); s.fail()
    assert s.history == before and not s.busy

def test_begin_while_busy_is_rejected():
    s = ChatSession(CFG); s.begin("a")
    assert s.begin("b") is None
    s.succeed("A"); assert [m["content"] for m in s.history] == ["a", "A"]

def test_only_last_turns_are_sent():
    s = ChatSession(CFG)
    for i in range(5): s.begin(f"q{i}"); s.succeed(f"a{i}")
    msgs = s.begin("now")["messages"]
    assert [m["content"] for m in msgs] == ["q3", "a3", "q4", "a4", "now"]

def test_blank_input_rejected():
    assert ChatSession(CFG).begin("   ") is None

def test_reset_clears():
    s = ChatSession(CFG); s.begin("a"); s.succeed("A"); s.reset(); assert s.history == []

def test_parse_delta_and_done():
    assert parse_stream_line(b'{"message":{"content":"\xec\x95\x88"},"done":false}') == ("안", False)
    assert parse_stream_line(b'{"message":{"content":""},"done":true}') == ("", True)

def test_blank_line_is_ignored():
    assert parse_stream_line(b"\n") == ("", False)

def test_error_line_raises():
    with pytest.raises(ChatError): parse_stream_line(b'{"error":"boom"}')

def test_garbage_line_raises():
    with pytest.raises(ChatError): parse_stream_line(b"<html>")

# ChatWorker: http.server로 로컬 가짜 서버를 띄워 검증
def test_worker_streams_then_done(fake_server, qapp):   # 두 조각 "안녕", "하세요" 후 done
    assert deltas == ["안녕", "하세요"] and done == ["안녕하세요"] and failed == []
def test_worker_connection_refused_reports_offline(qapp):   # 닫힌 포트
    assert failed == [MSG_OFFLINE]
def test_worker_404_reports_missing_model(fake_server_404, qapp):
    assert failed == ["'phoebe' 모델을 찾을 수 없어요."]
def test_worker_truncated_stream_reports_broken(fake_server_cut, qapp):   # done 없이 연결 종료
    assert failed == [MSG_BROKEN]
```

- [ ] **Step 2: 실행해 실패 확인.** `uv run pytest tests/test_chat.py -v` → FAIL.
- [ ] **Step 3: `chat.py` 구현.** `ChatWorker.run`은 `urllib.request`로 `{url}/api/chat`에 POST하고 응답을 줄 단위로 읽는다. 연결 제한 시간 5초, 읽기 제한 시간 180초(모델을 메모리에 올리는 시간 포함). 예외는 모두 잡아 `failed`로 내보내고, 어떤 경우에도 `done`과 `failed` 중 정확히 하나만 한 번 내보낸다.
- [ ] **Step 4: 통과 확인 후 커밋.** `git commit -m "feat: chat session and streaming Ollama worker"`

---

### Task 8: 말풍선·입력창과 대화 연결

**Files:**
- Create: `src/phoebe_pet/layout.py`, `src/phoebe_pet/bubble.py`
- Modify: `src/phoebe_pet/app.py`
- Test: `tests/test_layout.py`, `tests/test_bubble.py`

**Interfaces:**
- Consumes: `PetWindow.double_clicked`, `PetWindow.moved`, `Pet.begin_think/begin_talk/end_chat`, `ChatSession`, `ChatWorker`.
- Produces:
  ```python
  # layout.py
  def is_long(text: str) -> bool                     # 200자 초과, 6줄 초과, 또는 ``` 포함
  def hide_delay_ms(text: str) -> int                # 3000 + 60×글자수, 4000~30000으로 제한
  def place(anchor: QRect, size: QSize, bounds: QRect, gap: int = 8) -> QPoint
  # bubble.py
  class BubbleWindow(QWidget):
      def start(self) -> None                        # 비우고 표시 준비
      def append(self, delta: str) -> None
      def finish(self) -> None                       # 숨김 타이머 시작
      def show_notice(self, text: str) -> None       # 오류·안내 한 줄
      def follow(self, pet_rect: QRect) -> None
  class InputWindow(QWidget):
      submitted = Signal(str)
      def open_at(self, pet_rect: QRect) -> None
  ```

- [ ] **Step 1: 실패하는 테스트 작성**

```python
SCREEN = QRect(0, 0, 1920, 1040)
def test_bubble_sits_above_pet_centered():
    p = place(QRect(900, 900, 128, 128), QSize(300, 100), SCREEN)
    assert p == QPoint(900 + 64 - 150, 900 - 100 - 8)

def test_flips_below_when_no_room_above():
    assert place(QRect(900, 0, 128, 128), QSize(300, 100), SCREEN).y() == 128 + 8

def test_clamped_horizontally_at_edges():
    assert place(QRect(0, 900, 128, 128), QSize(300, 100), SCREEN).x() == 0
    assert place(QRect(1792, 900, 128, 128), QSize(300, 100), SCREEN).x() == 1920 - 300

def test_is_long():
    assert not is_long("안녕하세요, 방랑자님.")
    assert is_long("가" * 201) and is_long("a\n" * 7) and is_long("```py\nx\n```")

def test_hide_delay_bounds():
    assert hide_delay_ms("") == 4000 and hide_delay_ms("가" * 50) == 6000 and hide_delay_ms("가" * 9999) == 30000

# test_bubble.py (offscreen)
def test_bubble_never_takes_focus(bubble):
    assert bubble.windowFlags() & Qt.WindowDoesNotAcceptFocus
def test_append_accumulates(bubble):
    bubble.start(); bubble.append("안"); bubble.append("녕"); assert bubble.text() == "안녕"
def test_long_text_switches_to_scroll_mode(bubble):
    bubble.start(); bubble.append("가" * 300); assert bubble.is_scroll_mode()
def test_click_copies_text(bubble, qapp):
    bubble.start(); bubble.append("복사"); bubble.finish(); QTest.mouseClick(bubble, Qt.LeftButton)
    assert qapp.clipboard().text() == "복사"
def test_input_enter_submits_and_closes(inp):
    QTest.keyClicks(inp.edit, "hi"); QTest.keyClick(inp.edit, Qt.Key_Return)
    assert submitted == ["hi"] and not inp.isVisible()
def test_input_escape_closes_without_submit(inp):
    QTest.keyClick(inp.edit, Qt.Key_Escape); assert submitted == [] and not inp.isVisible()
def test_shift_enter_inserts_newline(inp):
    QTest.keyClicks(inp.edit, "a"); QTest.keyClick(inp.edit, Qt.Key_Return, Qt.ShiftModifier)
    assert submitted == [] and "\n" in inp.edit.toPlainText()
```

- [ ] **Step 2: 실행해 실패 확인.** `uv run pytest tests/test_layout.py tests/test_bubble.py -v` → FAIL.
- [ ] **Step 3: `layout.py`, `bubble.py` 구현.** 말풍선은 최대 폭 320px의 둥근 흰 상자에 꼬리, 글자는 `맑은 고딕` 10pt. 긴 글 모드는 최대 480×360px에 세로 스크롤, 고정폭 글꼴로 원문 그대로 표시(마크다운 렌더링 없음), 자동으로 사라지지 않고 바깥 클릭이나 Esc로 닫는다. 입력창은 캐릭터 옆(오른쪽에 자리가 없으면 왼쪽)에 뜨는 폭 280px 상자이며, 이 창만 포커스를 받는다. 안내 문구 `"Enter로 보내기 · Esc로 닫기"`를 placeholder로 둔다.
- [ ] **Step 4: `app.py`에 대화 흐름 연결.**
  - `double_clicked` → `pet.touch()`, 입력창 열기.
  - `submitted(text)` → `session.begin(text)`가 `None`이면 아무것도 하지 않는다. 아니면 `pet.begin_think()`, `ChatWorker` 시작.
  - 첫 `delta` → `pet.begin_talk()`, `bubble.start()`. 이후 `delta`마다 `bubble.append`.
  - `done(reply)` → `session.succeed(reply)`, `bubble.finish()`. 말풍선이 사라질 때(긴 글은 닫을 때) `pet.end_chat()`.
  - `failed(msg)` → `session.fail()`, `bubble.show_notice(msg)`, `pet.end_chat()`.
  - `PetWindow.moved` → `bubble.follow`.
  - 요청 후 8초가 지나도록 `delta`가 없으면 `bubble.show_notice("잠깐만요, 생각을 정리하고 있어요...")`를 띄운다(모델을 올리는 중일 때).
- [ ] **Step 5: 통과 확인.** `uv run pytest -v` → PASS.
- [ ] **Step 6: 직접 실행해 확인.** Ollama가 켜진 상태에서 `uv run python -m phoebe_pet`. 확인 항목: 더블클릭으로 입력창이 뜬다 / "안녕 페비" 전송 시 생각 중 동작 후 말풍선에 글자가 흘러나온다 / 답이 끝나면 말풍선이 사라지고 다시 돌아다닌다 / "파이썬으로 리스트 중복 제거 코드 써줘"는 스크롤 풍선으로 뜨고 클릭하면 복사된다 / Ollama를 끄고 보내면 `MSG_OFFLINE`이 뜬다. 화면을 캡처해 결과를 보고한다.
- [ ] **Step 7: 커밋.** `git commit -m "feat: speech bubble, input box and chat wiring"`

---

### Task 9: 트레이, 메뉴, 전체 화면 숨김, 혼잣말, 마무리

**Files:**
- Create: `src/phoebe_pet/fullscreen.py`, `README.md`, `run.bat`
- Modify: `src/phoebe_pet/app.py`
- Test: `tests/test_fullscreen.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `PetWindow.context_requested`, `Pet.set_paused`, `ChatSession.reset`, `Config.monologue`.
- Produces:
  ```python
  # fullscreen.py
  SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd"}
  def covers(win: tuple[int, int, int, int], mon: tuple[int, int, int, int]) -> bool
  def foreground_is_fullscreen() -> bool      # 앞 창이 모니터 전체를 덮고 셸 창이 아니면 True
  # app.py
  def build_menu(app_state) -> QMenu          # 트레이와 우클릭이 같이 쓴다
  MONOLOGUE_PROMPT = "(방랑자님이 한동안 말이 없다. 페비가 혼잣말처럼 한 문장만 가볍게 말을 건다.)"
  ```

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_covers():
    mon = (0, 0, 1920, 1080)
    assert covers((0, 0, 1920, 1080), mon) and covers((-8, -8, 1928, 1088), mon)
    assert not covers((0, 0, 1920, 1040), mon) and not covers((100, 100, 900, 700), mon)

def test_foreground_check_runs_without_error():
    assert foreground_is_fullscreen() in (True, False)

# test_app.py (offscreen)
def test_menu_items(menu):
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == ["일시정지", "대화 초기화", "숨기기", "종료"]

def test_pause_toggles_pet_and_label(menu, pet):
    act = menu.actions()[0]; act.trigger()
    assert pet.mode is Mode.PAUSED and act.text() == "다시 움직이기"
    act.trigger(); assert pet.mode is Mode.AUTO and act.text() == "일시정지"

def test_reset_clears_history(menu, session):
    session.begin("a"); session.succeed("A"); find(menu, "대화 초기화").trigger(); assert session.history == []

def test_hide_and_show(menu, win):
    act = find(menu, "숨기기"); act.trigger(); assert not win.isVisible() and act.text() == "보이기"
    act.trigger(); assert win.isVisible()

def test_fullscreen_hides_and_restores(app_state, win, monkeypatch):
    monkeypatch.setattr(fullscreen, "foreground_is_fullscreen", lambda: True); app_state.poll(); assert not win.isVisible()
    monkeypatch.setattr(fullscreen, "foreground_is_fullscreen", lambda: False); app_state.poll(); assert win.isVisible()

def test_fullscreen_does_not_override_manual_hide(app_state, win, menu, monkeypatch):
    find(menu, "숨기기").trigger()
    monkeypatch.setattr(fullscreen, "foreground_is_fullscreen", lambda: False); app_state.poll(); assert not win.isVisible()

def test_monologue_off_by_default_never_fires(app_state):
    app_state.idle_tick(seconds=3600); assert app_state.worker is None

def test_monologue_not_stored_as_user_turn(app_state_monologue_on, session):
    app_state_monologue_on.idle_tick(seconds=3600); app_state_monologue_on.finish_monologue("오늘 하늘이 맑네요.")
    assert session.history == [{"role": "assistant", "content": "오늘 하늘이 맑네요."}]
```

- [ ] **Step 2: 실행해 실패 확인.** `uv run pytest tests/test_fullscreen.py tests/test_app.py -v` → FAIL.
- [ ] **Step 3: `fullscreen.py` 구현.** `ctypes`로 `GetForegroundWindow`, `GetWindowRect`, `GetClassNameW`, `MonitorFromWindow`, `GetMonitorInfoW`. 실패하면 `False`.
- [ ] **Step 4: `app.py` 마무리.** 트레이 아이콘(`shime1` 그림)과 메뉴, 우클릭 메뉴 연결. `poll()`은 1초 주기 타이머로 전체 화면 여부를 확인한다. 숨겨진 동안에는 캐릭터 타이머를 멈춘다. 혼잣말은 `monologue`가 켜져 있고, 대화 중이 아니고, 마지막 상호작용 후 15~40분(매번 무작위)이 지났을 때 `MONOLOGUE_PROMPT`를 마지막 사용자 메시지로 붙여 요청하되 기록에는 답만 남긴다. `app.py`가 300줄을 넘으면 메뉴·트레이를 `tray.py`로 나눈다.
- [ ] **Step 5: `run.bat`, `README.md` 작성.** `run.bat`은 `uv run pythonw -m phoebe_pet`(콘솔 창 없이 실행). README는 한국어로: 실행 방법, 필요한 것(Ollama와 `ollama create phoebe -f Modelfile`), 조작법(끌기, 더블클릭, 우클릭), `config.toml` 항목, 캐릭터 교체 방법(`assets/<이름>/`에 `shime1.png`~ 를 넣고 `character` 변경, 선택 프레임 `talk*`, `think*`), 1차 버전에서 빠진 것.
- [ ] **Step 6: 전체 테스트.** `uv run pytest -v` → 전부 PASS.
- [ ] **Step 7: CPU 측정.** `run.bat`으로 띄우고 PowerShell에서 프로세스의 CPU 시간을 60초 간격으로 두 번 읽어 전체 CPU 대비 사용률을 계산한다(`(Δ CPU초 / 60 / 논리 코어 수) × 100`). 우클릭 `일시정지` 상태에서 1% 이하, 돌아다니는 상태에서 3% 이하여야 한다. 넘으면 원인을 찾아 고치고 다시 잰다. 측정값을 보고한다.
- [ ] **Step 8: 직접 실행해 확인.** 트레이 메뉴 네 항목이 동작한다 / 브라우저에서 영상을 전체 화면으로 하면 캐릭터가 사라지고 나오면 돌아온다 / 작업 표시줄을 자동 숨김으로 바꾸면 캐릭터가 새 바닥으로 내려온다.
- [ ] **Step 9: 커밋.** `git commit -m "feat: tray menu, fullscreen hiding, monologue and docs"`
