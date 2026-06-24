# Money Milestone — Android 앱 (Capacitor)

기존 Flask 웹(`https://moneymilestone.co.kr`)을 WebView로 감싼 안드로이드 앱.
UI/로직은 전부 서버에 있음 → **서버 코드 수정 = 앱에 자동 반영, 재배포 불필요.**

## 구조

- `capacitor.config.json` — `server.url`로 원격 prod 로드. `overrideUserAgent`로 WebView UA에서 `wv` 제거(구글 OAuth 차단 회피 시도).
- `www/` — 원격 로드 전 잠깐 보이는 폴백 화면.
- `android/` — 네이티브 Gradle 프로젝트 (Capacitor 생성).
- `assets/` — 아이콘/스플래시 원본(`logo.png`). `npx @capacitor/assets generate --android`로 재생성.

## 빌드 사전 준비 (이 PC에 아직 없음)

1. **Android Studio 설치** (Android SDK + JDK 17 번들). https://developer.android.com/studio
2. 설치 후 환경변수:
   - `ANDROID_HOME` = `%LOCALAPPDATA%\Android\Sdk`
   - `JAVA_HOME` = Android Studio 번들 JDK (예: `C:\Program Files\Android\Android Studio\jbr`)
   - 현재 이 PC는 **Java 8뿐** → AGP가 요구하는 **JDK 17+** 필요.

## 개발 빌드 (디버그 APK, 실기기 테스트)

```bash
cd mobile
npx cap sync android          # 설정/플러그인 동기화
npx cap open android          # Android Studio에서 열기 → Run ▶  (USB 디버깅 기기/에뮬레이터)
```

또는 CLI:
```bash
cd mobile/android
./gradlew assembleDebug       # 산출물: app/build/outputs/apk/debug/app-debug.apk
```

## 릴리스 빌드 (Play Store용 AAB)

1. **업로드 키 생성** (1회, 안전 보관 — 잃으면 앱 업데이트 불가):
   ```bash
   keytool -genkey -v -keystore moneymilestone-upload.jks \
     -keyalg RSA -keysize 2048 -validity 10000 -alias upload
   ```
2. `mobile/android/keystore.properties` 생성 (gitignore됨):
   ```properties
   storeFile=../../moneymilestone-upload.jks
   storePassword=<비밀번호>
   keyAlias=upload
   keyPassword=<비밀번호>
   ```
3. `android/app/build.gradle`에 서명 설정 연결 (signingConfigs → release). *Android Studio: Build > Generate Signed Bundle 메뉴가 더 쉬움.*
4. 빌드:
   ```bash
   cd mobile/android && ./gradlew bundleRelease
   # 산출물: app/build/outputs/bundle/release/app-release.aab
   ```
5. Play Console(개발자계정 $25 1회) → 앱 생성 → AAB 업로드 → 스토어 등록정보 작성 → 심사.

## ⚠️ 미해결 — 출시 전 반드시 확인

1. **구글 로그인(OAuth) in WebView**
   구글은 임베디드 WebView에서 OAuth를 막음(`disallowed_useragent`). `overrideUserAgent`로 1차 회피 시도함.
   - 실기기에서 로그인 **반드시 테스트**.
   - 막히면: 네이티브 구글 로그인 플러그인 + 백엔드 토큰 교환 엔드포인트 필요(서버 작업).
2. **Play "최소 기능" 정책** — 순수 웹뷰 앱은 반려 가능. 푸시알림 등 네이티브 기능 추가하면 통과율↑.
   - 이미 인앱 알림(celery) 있음 → FCM 푸시 연동이 다음 강화 포인트.
3. **딥링크/뒤로가기** — `@capacitor/app`로 안드로이드 백버튼 → WebView history.back 처리 추가 권장.
4. **앱 아이콘 화질** — 원본 logo.png가 390×390. 스토어용 512×512+ 권장 → 1024×1024 로고로 `assets generate` 재실행하면 선명.
