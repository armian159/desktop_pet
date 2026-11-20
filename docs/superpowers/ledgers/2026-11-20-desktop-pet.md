# SDD ledger — plan: docs/superpowers/plans/2026-11-20-desktop-pet.md
Setup: branch desktop-pet from 0c47e1c (master). Spec: docs/2026-11-20-desktop-pet-design.md
Pre-flight: T3->T5 Bounds/Body/step_air/clamp/MAX_DT — consistent. T4->T5 Action/Chooser/load_actions + special names — consistent. T5->T6 Pet/View/Mode, tests use pet._start — consistent. T1->T7 Config(history_turns, keep_alive, model, ollama_url) — consistent. T6->T8 PetWindow.double_clicked/moved — consistent. T7->T8/T9 ChatSession/ChatWorker — T9 monologue needs history append of assistant-only turn; ChatSession has no such method. Ruling: T9 adds ChatSession.add_assistant(text) — smallest change satisfying spec's monologue — if wrong, one extra public method.
Task 1: complete (commits 0c47e1c..b2b8e94, tests: uv run pytest -q → 8 passed in 4.98s)
Task 2: Step 1 verified against gil/shimeji-ee conf/actions.xml (fetched). Plan table matches except: Pinched uses 5 tilt frames 9,7,1,8,10 (not 7); shime5/6 are "Resisting" (struggle while held).
Task 2: Ruling: drag = 5 tilt frames by horizontal speed (fast-left 10, 8, 1, 7, fast-right 9) + "resist" special (5,6 alternating) when held still >1s — original standard wins per spec — if wrong, drag looks different from classic Shimeji.
Task 2: Ruling: original uses image anchors (ceiling 64,48; leg-dangle sits 64,112; wall anchor x=64 puts image centre on the wall line). Real image sets only look right if honoured, so actions get an `offset=[dx,dy]` (unscaled, left-facing) and View gains `offset: tuple[int,int]`; View.x/y stay the logical 128-box so plan tests hold. Costs if wrong: wall/ceiling sprites drawn shifted.
Task 2: complete (commits b2b8e94..2e09d22, tests: uv run pytest -q → 18 passed in 0.26s)
Task 3: complete (commits 2e09d22..d66065f, tests: uv run pytest -q → 29 passed in 0.29s)
Task 4: complete (commits d66065f..d93f77b, tests: uv run pytest -q → 43 passed in 0.38s)
Task 5: Note: idle weights/durations in actions.toml retuned from the plan's table (stand 6/4, walk idle 4, sit idle 4 dur 3-8, lie idle 2 dur 5-12, sit_dangle idle 2) — plan values left the pet sitting/lying ~80% of unattended time; spec leaves weights to the builder.
Task 5: complete (commits d93f77b..6d5893c, tests: uv run pytest -q → 84 passed in 4.52s)
Task 6: Step 6 live check (17s on real 2560x1392 screen, scripted): stand/sit/lie on taskbar top, wall hold+climb at x=-64 offset, grab+throw+land, adaptive timer 100/16ms, pet hwnd never foreground. Manual mouse-drag and click-through-on-transparent not exercised by me (no input automation) — covered by widget tests + mask test only.
Task 6: complete (commits 6d5893c..ff5723c, tests: uv run pytest -q → 96 passed in 4.60s)
Task 7: Ruling: urllib has one timeout, so connect and read both use 180s instead of the plan 5s/180s split — refused localhost connections fail instantly anyway — cost: a black-holed non-local ollama_url would wait 3 min before reporting.
Task 8: Ruling: long (scroll) bubble closes via its own close button and has a copy button, instead of "outside click or Esc" — the bubble must never take focus (spec anti-goal) so it cannot receive Esc, and outside-click needs a global mouse hook — cost: one extra click target.
Task 8: Ruling: wiring lives in a PetApp class with an injectable worker factory so the chat flow is unit-tested, not only checked by hand — cost: none beyond a constructor argument.
Task 7: complete (commits ff5723c..534e9ff, tests: uv run pytest -q tests/test_chat.py tests/test_pet.py tests/test_pet_window.py tests/test_physics.py tests/test_behavior.py tests/test_frames.py tests/test_sprites.py tests/test_config.py → 115 passed in 9.67s)
Task 8: Step 6 live check against real Ollama (phoebe): input box beside pet, think frames while waiting 9s, streaming bubble, reply recorded, bubble auto-closed, long code reply in scroll bubble, copy button matched clipboard, close button ended chat, 2 turns in history. Ollama-off message verified by unit test on a refused port only (did not stop the user's Ollama).
Task 8: complete (commits 534e9ff..12e5d37, tests: uv run pytest -q → 147 passed in 11.16s)
Task 9: Step 7 CPU on real screen, 20s each, 16 logical cores: forced moving 8.51% of one core = 0.53% total; paused 0.00%; free roaming 0.22% total. Targets 3% / 1% met. Step 8 (fullscreen video, taskbar auto-hide) not exercised by hand — covered by unit tests with a patched detector and Pet.set_bounds tests; foreground_is_fullscreen ran against the real desktop without error. app.py is 271 lines (<300), not split.
Task 9: complete (commits 12e5d37..7e2de27, tests: uv run pytest -q → 163 passed in 11.36s)
Final review: fresh reviewer (most capable model), verdict "with fixes": 0 Critical, 5 Important, 10 Minor.
Final: fixed I-1 bubble reappearing over fullscreen/hidden pet while a request is in flight — tests/test_hidden_chat.py (suppress tests, streaming/wait-notice/error while hidden) RED→GREEN, suite 207/207
Final: fixed I-2 pet stuck in TALK when the reply finished while hidden — test_reply_finished_while_hidden_is_shown_on_return_and_chat_ends, test_hiding_after_the_reply_is_up_does_not_strand_the_pet RED→GREEN, suite 207/207
Final: fixed I-3 maximized window + auto-hide taskbar counted as fullscreen — test_maximized_titled_window_is_not_fullscreen_even_with_hidden_taskbar RED→GREEN, suite 207/207. Not confirmed on a real auto-hide taskbar or a real fullscreen video.
Final: fixed I-4 primary screen replaced/removed left stale bounds — test_follow_screen_moves_the_pet_into_that_screen RED→GREEN, suite 207/207; main() now follows primaryScreenChanged.
Final: fixed I-5 actions.toml validation holes — test_real_app_needs_its_fixed_actions, test_empty_file_is_reported_not_crashed, test_wrong_types_raise_value_error, test_action_table_of_wrong_shape_raises_value_error, test_next_must_stay_on_the_same_surface RED→GREEN, suite 207/207
Final: Ruling: reviewer declined to judge blurry sprites above 100% display scaling — stands for now: spec is silent and the user's screen reports devicePixelRatio 1.0 — cost: soft-looking sprite on a scaled display.
Final: Ruling: reviewer declined to judge history_turns=12 overflowing the 8192-token context with long code replies — stands: spec asks for "recent N turns"; Ollama truncates the oldest context rather than failing — cost: the persona examples could be pushed out in a very long technical chat.
Final: Ruling: reviewer declined to judge a fullscreen window on another monitor hiding the pet — stands: multi-monitor is out of scope in the spec — cost: pet hides when it need not.
Final: Ruling: reviewer could not check on a real device that the popup menu closes on an outside click, that transparent pixels pass clicks, and mask edge quality — unverified by me as well (no input automation); the user dragging the pet during the live chat check shows mouse input reaches it — cost: a usability bug only the user can see.
Final: minor (deferred): M-1 bounds growing during the 0.4s landing squash can leave the pet standing above the new floor until the next drag/bounds change
Final: minor (deferred): M-2 a monologue that fails mid-stream leaves a half-written bubble with no hide timer (monologue=true only)
Final: minor (deferred): M-3 quitting while waiting on a blocked read may destroy a running QThread (wait(2000) can time out)
Final: minor (deferred): M-4 a message sent while a reply is streaming is cleared from the input box and silently dropped
Final: minor (deferred): M-5 the pet keeps wandering while the input box is open; it only stops when the message is sent
Final: minor (deferred): M-6 fullscreen hide or the popup menu during a drag may leave the pet stuck to the cursor (not reproduced)
Final: minor (deferred): M-7 ollama_url without http:// shows the "connection dropped" message instead of a config error
Final: minor (deferred): M-8 frames smaller than shime1 are scaled up to fill the box
Final: minor (deferred): M-9 monologue lines are assistant-only history entries, so user/assistant pairing in the sent window can be off by one
Final: minor (deferred): M-10 no test for M-1
Extra (user request after the plan): tools/import_sheet.py sprite-sheet importer + tests (20), commit 06ccaaf. Thin dark antialiased lines on a JPEG green sheet keep a faint green fringe; tolerance flag is the only control.
