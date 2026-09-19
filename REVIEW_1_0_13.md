# 1.0.13 전체 소스 점검 기록

1.0.12 배포를 기준으로 전체 프로그램 Python 모듈과 Windows 실행·설치·빌드 스크립트를 읽고 연결 경로를 검토했습니다. 정적 검토는 모든 동작이 실제 Windows 게임 환경에서 검증됐다는 뜻은 아닙니다.

## 수정

- 미완료 잔액 기록이 시간·아이템 측정 시작을 막지 않도록 분리. 이전 잔액은 보존하고 오래된 자동 종료 요청은 취소합니다. 이전 기록을 자동으로 합산하거나 종료하지 않습니다.
- 타이머 예약을 부가 화면 갱신과 분리. 화면 갱신 예외 후에도 다음 타이머/이벤트 콜백을 유지합니다. 오류는 로컬 callback_error.txt에 남습니다.
- 중복 시작으로 시간 기준이 바뀌지 않도록 방어. 작업 스레드 시작 실패 시 실행 상태 복구.
- 종료 시 먼저 정지·저장. 회차 시간은 단조 시계의 측정분을 사용하고, 비정상 종료 복구에 프로그램이 꺼져 있던 시간을 더하지 않습니다. 구형 기록에 측정 체크포인트가 없으면 시간을 추정하지 않습니다.
- Windows 글씨 배율 상한과 더 작은 목록·요약 글씨 적용. 캡처용 DPI 인식은 유지합니다. 왼쪽/위쪽 보조 모니터 영역 선택 창은 절대 좌표로 배치합니다.
- 목록 갱신을 행 전체 삭제 대신 기존 행 갱신으로 변경하여 다중 선택·스크롤·포커스를 유지합니다.
- 오늘 목록 비우기 전의 보존 기록도 수익 예상의 단가 등록 여부 판정에 포함합니다.
- 스킬 시간에 NaN/무한대 입력을 거부하고 자동 감지 해제 시 버튼 상태를 즉시 갱신합니다.
- 저장 파일의 지수 표기 오버플로도 비정상 숫자로 처리하여 정상 백업 복구 경로를 사용합니다.
- API 키 삭제 시 일정 조회의 메모리 키와 이전 결과를 무효화합니다.
- 설정 화면의 실제 업데이트 버튼에 새 버전·다운로드 상태가 표시되도록 연결합니다.
- 업데이트 패키지에 로컬 Python 의존 모듈을 포함하여 예전 패치 구성 차이에 의존하지 않게 합니다. 설정·모델·개인 기록은 배포 파일에 포함하지 않습니다.

## 검토 범위

- 실행/표시: launch, maple_loot_counter, display_setup, clean_ui, all_items_ui, modern_ui, first_run, window_controls
- 기록/수익: settings_store, instance_lock, daily_records, smart_features, loot_prices, price_ui, goal_ui, wallet_tracker, wallet_auto, wallet_state
- 화면/OCR: paddle_backend, ocr_engine, recognition_state, recognition_trace, chat_tracker, chat_windows, tracking_profiles
- 스킬/버프: skill_timers, skill_worker, quickslot_auto, quickslot_picker, hunting_buffs, hunting_meso
- API/아이콘: hunting_api, scheduler_api, scheduler_ui, api_key_store, item_icons, item_icon_data(정적 데이터)
- 배포/설치: app_updater, updater_ui, setup_ocr, build_exe, self_test, run.bat, install_and_run.bat, build_exe.bat, requirements.txt

## 검증과 한계

- 프로그램 Python 모듈 43개와 실행 스크립트 정적 검토. 전체 로컬 회귀 테스트 172개 통과.
- 실제 배포 JSON에서 모듈을 추출한 회귀 테스트 61개 통과(로컬 테스트와 중복되는 항목 포함). 로컬 소스에만 있고 배포 패키지에는 빠진 의존 파일도 점검.
- 포함된 실제 OCR 모델·샘플로 아이템 이름·수량 10/10 통과.
- 과거 전체 ZIP에 새 패키지를 적용하여 파일 교체, 백업, 설정·모델 보존 및 문법 검증.
- Windows 게임 화면, 전역 키 입력, 실제 DPI 전환, DPAPI, Windows EXE 빌드 및 실서비스 API 호출은 이 Linux 환경에서 종단 간 검증하지 못했습니다.
- 전체 코드 검토와 테스트 통과는 미발견 오류가 없다는 보장이 아닙니다. 자동 OCR 특성상 가림·동일 문장 반복·빠른 스크롤 구간의 누락 가능성은 유지됩니다.
