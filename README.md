# 페비 데스크톱 펫

바탕화면을 돌아다니는 작은 캐릭터입니다. 더블클릭하면 로컬에서 도는 Ollama 모델과 말풍선으로 대화합니다.

## 필요한 것

- Windows 11, Python 3.12, [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com)와 `phoebe` 모델

모델은 이 폴더의 `Modelfile`로 만듭니다.

```
ollama pull qwen3:8b
ollama create phoebe -f Modelfile
```

## 실행

`run.bat`을 더블클릭하면 콘솔 창 없이 실행됩니다. 터미널에서 띄우려면:

```
uv run python -m phoebe_pet
```

## 조작

| 동작 | 결과 |
|---|---|
| 누른 채 끌기 | 집어 듭니다. 놓으면 마우스 속도대로 던져집니다 |
| 더블클릭 | 입력창이 열립니다. Enter로 보내고 Esc로 닫습니다. Shift+Enter는 줄바꿈 |
| 말풍선 클릭 | 내용을 클립보드에 복사합니다 |
| 우클릭, 트레이 아이콘 | 일시정지, 대화 초기화, 숨기기, 종료 |

긴 답이나 코드는 스크롤되는 큰 말풍선으로 뜨고, `복사`와 `닫기` 버튼이 붙습니다.
전체 화면 프로그램을 쓰는 동안에는 캐릭터가 숨습니다.

## 설정 (`config.toml`)

| 항목 | 기본값 | 설명 |
|---|---|---|
| `character` | `placeholder` | `assets/` 아래 캐릭터 폴더 이름 |
| `scale` | `1.0` | 크기 배율 (0.25 ~ 4.0) |
| `model` | `phoebe` | Ollama 모델 이름 |
| `ollama_url` | `http://localhost:11434` | Ollama 주소 |
| `speed` | `1.0` | 이동 속도 배율 (0.25 ~ 4.0) |
| `monologue` | `false` | 15~40분간 말이 없으면 먼저 말을 겁니다 |
| `history_turns` | `12` | 모델에 보내는 최근 대화 턴 수 |
| `keep_alive` | `30m` | 모델을 메모리에 유지하는 시간 |

설정을 바꾼 뒤에는 앱을 다시 실행합니다.

## 캐릭터 바꾸기

시메지(Shimeji) 규격 이미지 세트를 그대로 쓸 수 있습니다.

1. `assets/<이름>/` 폴더를 만들고 `shime1.png`, `shime2.png` … 를 넣습니다. 투명 배경 PNG이고, 캐릭터는 왼쪽을 봅니다.
2. `config.toml`의 `character`를 `<이름>`으로 바꿉니다.

`shime1.png`만 있어도 실행됩니다. 없는 그림은 가장 비슷한 동작의 그림으로 대신합니다.
말할 때와 생각할 때 전용 그림을 쓰려면 `talk1.png`, `talk2.png`, `think1.png`, `think2.png`를 추가합니다.

`assets/placeholder`는 임시 캐릭터이고 `uv run python tools/make_placeholder.py`로 다시 만들 수 있습니다.
그 밖의 캐릭터 폴더는 git에 올라가지 않습니다.

## 동작 조정

동작의 종류, 그림 순서, 속도, 지속 시간, 뽑힐 확률은 `actions.toml`에 있습니다. 파일 맨 위에 각 항목 설명이 있습니다.

## 아직 없는 것

- 음성 입출력
- 일정·이슈 조회처럼 실제로 뭔가를 실행하는 비서 기능
- 다른 프로그램 창 위에 올라타기, 여러 모니터
- 대화 기록 저장 (앱을 끄면 사라집니다)

## 개발

```
uv run pytest
```

설계와 구현 계획은 `docs/`에 있습니다.
